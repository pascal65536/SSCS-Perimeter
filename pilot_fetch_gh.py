import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = os.environ.get("GITHUB_TOKEN", "")
UA = {
    "User-Agent": "sscs-monitor/0.1 (diploma research; pilot phase 2)",
    "Accept": "application/vnd.github+json",
}
if TOKEN:
    UA["Authorization"] = f"Bearer {TOKEN}"

# Ground truth-репозитории (Приложение Б): npm-инциденты + ultralytics
DEFAULT_REPOS = {
    "dominictarr/event-stream": {
        "since": "2018-08-01T00:00:00Z",
        "until": "2018-12-31T00:00:00Z",
        "package_name": "event-stream",
        "watchlist": "ground_truth",
    },
    "faisalman/ua-parser-js": {
        "since": "2021-09-01T00:00:00Z",
        "until": "2021-11-30T00:00:00Z",
        "package_name": "ua-parser-js",
        "watchlist": "ground_truth",
    },
    "ultralytics/ultralytics": {
        "since": "2024-11-01T00:00:00Z",
        "until": "2024-12-31T00:00:00Z",
        "package_name": "ultralytics",
        "watchlist": "ground_truth",
    },
}
MAX_PRS = 300  # потолок PR на репозиторий (квота)
CRITICAL = re.compile(
    r"(setup\.py|setup\.cfg|pyproject\.toml|__init__\.py|"
    r"\.github/workflows/|package\.json|requirements|publish|release)",
    re.IGNORECASE,
)


def gh(path, params=None):
    url = "https://api.github.com" + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
                reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                if remaining < 50 and reset:
                    wait = max(1, reset - int(time.time()) + 1)
                    print(f"  ~ квота: пауза {wait}s", flush=True)
                    time.sleep(wait)
                return resp.status, body
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 2:
                time.sleep(30)
                continue
            return e.code, None
        except Exception as e:
            return f"error:{type(e).__name__}", None
    return "error:retries", None


def paginate(path, params, cap):
    out, page = [], 1
    while len(out) < cap:
        p = dict(params, page=page, per_page=100)
        status, body = gh(path, p)
        if status != 200 or not body:
            break
        out.extend(body)
        if len(body) < 100:
            break
        page += 1
        time.sleep(0.3)
    return out[:cap]


def fetch_repo(repo, cfg):
    owner_name = repo
    commits = []
    for c in paginate(
        f"/repos/{repo}/commits", {"since": cfg["since"], "until": cfg["until"]}, 5000
    ):
        commits.append(
            {
                "sha": c["sha"],
                "login": (c.get("author") or {}).get("login"),
                "message": (c.get("commit") or {}).get("message", "")[:120],
                "additions": None,
                "deletions": None,
                "files_changed": None,
                "is_merge": len(c.get("parents", [])) > 1,
                "committed_at": c["commit"]["committer"]["date"],
            }
        )

    prs = []
    for pr in paginate(
        f"/repos/{repo}/pulls",
        {"state": "all", "sort": "created", "direction": "asc"},
        MAX_PRS,
    ):
        created = pr["created_at"]
        if created < cfg["since"] or created > cfg["until"]:
            continue
        number = pr["number"]
        reviews, files = [], []
        if pr.get("merged_at"):
            _, reviews = gh(f"/repos/{repo}/pulls/{number}/reviews", {"per_page": 100})
            _, files = gh(f"/repos/{repo}/pulls/{number}/files", {"per_page": 100})
            reviews = reviews or []
            files = files or []
            time.sleep(0.3)
        prs.append(
            {
                "number": number,
                "author": (pr.get("user") or {}).get("login"),
                "created_at": created,
                "merged_at": pr.get("merged_at"),
                "merged_by": ((pr.get("merged_by") or {}) or {}).get("login"),
                "review_count": len(reviews),
                "touches_critical": bool(files)
                and any(CRITICAL.search(f.get("filename", "")) for f in files),
                "author_first_contrib_at": None,
            }
        )

    first_contrib = {}
    for c in commits:
        login = c["login"]
        if login and login not in first_contrib:
            first_contrib[login] = c["committed_at"]
    for pr in prs:
        pr["author_first_contrib_at"] = first_contrib.get(pr["author"])

    members, profiles = [], []
    _, coll = gh(f"/repos/{repo}/collaborators", {})
    if isinstance(coll, list):
        for m in coll[:20]:
            login = m.get("login")
            _, prof = gh(f"/users/{login}", {})
            if isinstance(prof, dict):
                profiles.append(
                    {
                        "login": login,
                        "date": cfg["until"][:10],
                        "account_created_at": prof.get("created_at"),
                        "followers": prof.get("followers"),
                        "public_repos": prof.get("public_repos"),
                    }
                )
            members.append(
                {
                    "login": login,
                    "role": "maintainer",
                    "change_type": "added",
                    "event_at": cfg["since"],
                }
            )
            time.sleep(0.3)

    snapshots = []
    _, repo_info = gh(f"/repos/{repo}", {})
    if isinstance(repo_info, dict):
        snapshots.append(
            {
                "date": cfg["until"][:10],
                "stars": repo_info.get("stargazers_count"),
                "forks": repo_info.get("forks_count"),
                "watchers": repo_info.get("subscribers_count"),
                "open_issues": repo_info.get("open_issues_count"),
                "open_prs": None,
            }
        )
    return {
        "kind": "github_repo",
        "watchlist": cfg["watchlist"],
        "repo": repo,
        "package_name": cfg.get("package_name"),
        "commits": commits,
        "pull_requests": prs,
        "snapshots": snapshots,
        "members": members,
        "profiles": profiles,
    }


def main():
    repos = DEFAULT_REPOS
    if os.environ.get("REPOS"):
        repos = {
            r: DEFAULT_REPOS.get(
                r,
                {
                    "since": "2015-01-01T00:00:00Z",
                    "until": "2026-12-31T00:00:00Z",
                    "watchlist": "ground_truth",
                },
            )
            for r in os.environ["REPOS"].split(",")
        }
    out_dir = Path("pilot/gh_fixtures")
    out_dir.mkdir(parents=True, exist_ok=True)
    if not TOKEN:
        print(
            "ВНИМАНИЕ: GITHUB_TOKEN не задан — лимит 60 req/час, прогон не завершится."
        )
    for repo, cfg in repos.items():
        path = out_dir / (repo.replace("/", "__") + ".json")
        if path.exists():
            print(f"[skip] {repo} (resume)", flush=True)
            continue
        print(f"[fetch] {repo} ...", flush=True)
        status_or_fixture = None
        try:
            fixture = fetch_repo(repo, cfg)
            path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            print(
                f"  commits={len(fixture['commits'])} prs={len(fixture['pull_requests'])} "
                f"profiles={len(fixture['profiles'])}",
                flush=True,
            )
        except Exception as e:
            print(f"  ! ошибка {repo}: {type(e).__name__}: {e}", flush=True)
    print("готово", flush=True)


if __name__ == "__main__":
    main()
