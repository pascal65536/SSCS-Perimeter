from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collector import normalize, state as state_mod
from collector.collectors import github as gh
from collector.collectors import pypi as py
from spool import DiskSpool

LOG = logging.getLogger(__name__)


class ApiClient:
    def __init__(self, *, timeout: int = 20, min_interval: float = 0.0, github: bool = False):
        self.timeout = timeout
        self.min_interval = min_interval
        self.github = github
        self._last = 0.0
        self._lock = threading.Lock()

    def get(self, url: str) -> Any:
        headers = {"Accept": "application/vnd.github+json" if self.github else "application/json", "User-Agent": "SSCS-Perimeter/1.2"}
        if self.github:
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        for attempt in range(3):
            with self._lock:
                pause = self.min_interval - (time.monotonic() - self._last)
                if pause > 0:
                    time.sleep(pause)
                self._last = time.monotonic()
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise
                if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                    raise
                remaining = exc.headers.get("X-RateLimit-Remaining")
                retry = exc.headers.get("Retry-After")
                if retry:
                    pause = float(retry)
                elif remaining == "0" and exc.headers.get("X-RateLimit-Reset"):
                    pause = max(0.0, float(exc.headers["X-RateLimit-Reset"]) - time.time())
                else:
                    pause = 2**attempt
                time.sleep(pause)
        raise AssertionError("unreachable")


class PyPIPoller:
    def __init__(self, client: ApiClient | None = None):
        self.client = client or ApiClient(min_interval=0.3)

    def events(self, package: dict, watchlist: str, reference: list[str], ingested_at: str) -> list[dict]:
        name = package["name"]
        data = self.client.get(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
        repo = package.get("repo")
        info = data.get("info") or {}
        fixture = {
            "info": {"name": info.get("name", name), "version": info.get("version"), "uploader": info.get("uploader"), "requires_dist": info.get("requires_dist") or []},
            "releases": data.get("releases") or {},
        }
        result = [normalize.normalize_pypi_created(py.collect_pypi_created(fixture, reference), watchlist=watchlist, repo=repo, ingested_at=ingested_at)]
        for version, files in sorted((data.get("releases") or {}).items()):
            files = [f for f in files or [] if f.get("upload_time") or f.get("upload_time_iso_8601")]
            if not files:
                continue
            files.sort(key=lambda f: f.get("upload_time") or f.get("upload_time_iso_8601"))
            first = files[0]
            src = {
                "name": name,
                "version": version,
                "released_at": first.get("upload_time") or first.get("upload_time_iso_8601"),
                "uploader": info.get("uploader"),
                "size": first.get("size"),
                "yanked": bool(first.get("yanked")),
                "requires_dist": info.get("requires_dist") or [],
                "sha256": (first.get("digests") or {}).get("sha256"),
            }
            result.append(normalize.normalize_pypi_release(src, watchlist=watchlist, repo=repo, ingested_at=ingested_at))
        return result


class GitHubPoller:
    def __init__(self, client: ApiClient | None = None):
        self.client = client or ApiClient(github=True)

    def events(self, package: dict, watchlist: str, ingested_at: str) -> list[dict]:
        repo = package["repo"]
        name = package["name"]
        base = f"https://api.github.com/repos/{repo}"
        today = ingested_at[:10]
        snapshot = self.client.get(base)
        result = [normalize.normalize_repo_snapshot(gh.collect_repo_snapshot({"repo": repo, "snapshot": {
            "date": today, "stars": snapshot.get("stargazers_count"), "forks": snapshot.get("forks_count"),
            "watchers": snapshot.get("subscribers_count"), "open_issues": snapshot.get("open_issues_count"), "open_prs": None,
        }}), watchlist=watchlist, ingested_at=ingested_at)]
        commits = self.client.get(f"{base}/commits?per_page=100")
        profiles: dict[str, dict] = {}
        for item in commits or []:
            commit = item.get("commit") or {}
            author = item.get("author") or {}
            src = gh.collect_repo_commit({"repo": repo, "package_name": name, "commit": {
                "sha": item["sha"], "login": author.get("login"), "message": (commit.get("message") or "").splitlines()[0],
                "additions": None, "deletions": None, "files_changed": None,
                "is_merge": len(item.get("parents") or []) > 1,
                "committed_at": (commit.get("committer") or {}).get("date"),
            }})
            result.append(normalize.normalize_github_commit(src, watchlist=watchlist, ingested_at=ingested_at))
            login = author.get("login")
            if login and login not in profiles:
                profiles[login] = self._profile(login)
        pulls = self.client.get(f"{base}/pulls?state=all&sort=created&direction=desc&per_page=100")
        for item in pulls or []:
            number = item["number"]
            detail = self.client.get(f"{base}/pulls/{number}")
            reviews = self.client.get(f"{base}/pulls/{number}/reviews?per_page=100")
            files = self.client.get(f"{base}/pulls/{number}/files?per_page=100")
            login = (item.get("user") or {}).get("login")
            if login and login not in profiles:
                profiles[login] = self._profile(login)
            profile = profiles.get(login, {}) if login else {}
            filenames = [f.get("filename", "") for f in files or []]
            critical = any(f in {"setup.py", "pyproject.toml", "__init__.py"} or f.startswith(".github/workflows/") for f in filenames)
            first = self._first_contribution(base, login, item["created_at"]) if login else None
            src = gh.collect_repo_pull_request({"repo": repo, "package_name": name, "pull_request": {
                "number": number, "author": login, "created_at": item["created_at"], "merged_at": detail.get("merged_at"),
                "merged_by": (detail.get("merged_by") or {}).get("login"), "review_count": len(reviews or []),
                "touches_critical": critical, "author_first_contrib_at": first,
                "author_account_created_at": profile.get("created_at"),
            }})
            result.append(normalize.normalize_github_pr(src, watchlist=watchlist, ingested_at=ingested_at))
        for login, profile in sorted(profiles.items()):
            if profile:
                src = gh.collect_user_profile_snapshot({"profile": {
                    "login": login, "date": today, "account_created_at": profile.get("created_at"),
                    "followers": profile.get("followers"), "public_repos": profile.get("public_repos"),
                }})
                result.append(normalize.normalize_user_profile_snapshot(src, watchlist=watchlist, ingested_at=ingested_at))
        return result

    def _profile(self, login: str) -> dict:
        return self.client.get(f"https://api.github.com/users/{urllib.parse.quote(login)}")

    def _first_contribution(self, base: str, login: str, before: str) -> str | None:
        query = urllib.parse.urlencode({"author": login, "until": before, "per_page": 100})
        commits = self.client.get(f"{base}/commits?{query}") or []
        dates = [(c.get("commit") or {}).get("author", {}).get("date") for c in commits]
        dates = [d for d in dates if d]
        # Полная страница не доказывает отсутствие более ранней истории: не создаём FP.
        if len(commits) >= 100:
            return None
        return min(dates) if dates else None


class PerimeterCollector:
    def __init__(self, settings: dict, spool: DiskSpool, state_path: str | Path, *, pypi: PyPIPoller | None = None, github: GitHubPoller | None = None):
        self.settings = settings
        self.spool = spool
        self.state_path = Path(state_path)
        self.pypi = pypi or PyPIPoller()
        self.github = github or GitHubPoller()

    def run_once(self, *, ingested_at: str | None = None) -> dict[str, Any]:
        stamp = ingested_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = state_mod.load(self.state_path)
        known = set(state.last_seen_event_ids)
        packages = sorted(self.settings["perimeter"]["packages"], key=lambda p: p["name"])
        candidates: list[dict] = []
        warnings: list[str] = []
        workers = min(8, self.settings["polling"].get("max_workers", 8))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._collect_package, pkg, stamp): pkg for pkg in packages}
            for future in as_completed(futures):
                pkg = futures[future]
                try:
                    candidates.extend(future.result())
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        is_github = "api.github.com" in (exc.url or "")
                        candidates.append(self._removed(pkg, stamp, github=is_github))
                        warnings.append(f"{pkg['name']}: ресурс исчез (HTTP 404), создано семантическое событие")
                    else:
                        warnings.append(f"{pkg['name']}: HTTP {exc.code}; цикл продолжен")
                except Exception as exc:
                    warnings.append(f"{pkg['name']}: {type(exc).__name__}; цикл продолжен")
        accepted_ids = []
        rejected = 0
        for event in sorted(candidates, key=lambda e: e["event"]["id"]):
            event_id = event["event"]["id"]
            if event_id in known:
                continue
            if self.spool.enqueue(event):
                accepted_ids.append(event_id)
            else:
                rejected += 1
        state_mod.save(self.state_path, state_mod.make_state(accepted_ids + state.last_seen_event_ids, stamp))
        return {"seen": len(candidates), "new": len(accepted_ids), "duplicates": len(candidates) - len(accepted_ids) - rejected, "rejected": rejected, "warnings": sorted(warnings)}

    def _collect_package(self, package: dict, stamp: str) -> list[dict]:
        events = self.pypi.events(package, "monitored", self.settings["reference"], stamp)
        if package.get("repo"):
            events.extend(self.github.events(package, "monitored", stamp))
        roots = package.get("perimeter_root") or [self.settings["project"]["name"]]
        return [normalize.with_perimeter_root(event, roots) for event in events]

    def _removed(self, package: dict, stamp: str, *, github: bool = False) -> dict:
        name = package["name"]
        date = stamp[:10].replace("-", "")
        event_id = f"gh:{package['repo'].lower()}:removed:{date}" if github else f"pypi:{name}:removed:{date}"
        event = {
            "@timestamp": stamp,
            "event": {"id": event_id, "kind": "event", "category": "code_change" if github else "package", "type": "deletion", "action": "repo.removed" if github else "package.removed", "ingested": stamp, "outcome": "unknown"},
            "source": {"service": "github-api" if github else "pypi-api", "component": "github-rest" if github else "pypi-json"},
            "package": {"name": name, "registry": "pypi"},
            "sscs": {"schema_version": "1.0", "watchlist": "monitored", "repo": package.get("repo"), "point_in_time": True, "perimeter_root": package.get("perimeter_root") or [self.settings["project"]["name"]]},
        }
        return event
