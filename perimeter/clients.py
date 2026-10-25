from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .http import JsonHttpClient, quoted


class DepsDevClient:
    def __init__(self, http: JsonHttpClient | None = None, base_url: str = "https://api.deps.dev/v3"):
        self.http = http or JsonHttpClient(timeout=20, min_interval=0.05)
        self.base_url = base_url.rstrip("/")

    def dependencies(self, name: str, version: str) -> dict[str, Any]:
        url = (
            f"{self.base_url}/systems/pypi/packages/{quoted(name)}"
            f"/versions/{quoted(version)}:dependencies"
        )
        return self.http.get(url)


class PyPIClient:
    def __init__(self, http: JsonHttpClient | None = None, base_url: str = "https://pypi.org/pypi"):
        self.http = http or JsonHttpClient(timeout=20, min_interval=0.3)
        self.base_url = base_url.rstrip("/")

    def package(self, name: str) -> dict[str, Any]:
        return self.http.get(f"{self.base_url}/{quoted(name)}/json")


def normalize_github_repo(data: dict[str, Any]) -> str | None:
    """Извлекает owner/repo из PyPI project_urls/home_page без доверия к порядку ссылок."""
    info = data.get("info") or {}
    candidates: list[tuple[int, str]] = []
    priority = {
        "source": 0,
        "source code": 0,
        "repository": 0,
        "github": 0,
        "code": 1,
        "homepage": 2,
        "home page": 2,
    }
    for key, value in (info.get("project_urls") or {}).items():
        if isinstance(value, str):
            candidates.append((priority.get(key.lower(), 3), value))
    if isinstance(info.get("home_page"), str):
        candidates.append((2, info["home_page"]))
    for _, url in sorted(candidates, key=lambda x: (x[0], x[1])):
        match = re.search(r"(?:https?://|git@)github\.com[:/]([^/]+)/([^/#?]+)", url, re.I)
        if match:
            owner, repo = match.groups()
            repo = re.sub(r"\.git/?$", "", repo, flags=re.I).strip("/")
            if owner and repo:
                return f"{owner}/{repo}"
    return None


def package_metadata(data: dict[str, Any], *, history_limit: int = 12) -> dict[str, Any]:
    info = data.get("info") or {}
    releases: list[dict[str, str]] = []
    for version, files in (data.get("releases") or {}).items():
        dates = [
            f.get("upload_time_iso_8601") or f.get("upload_time")
            for f in (files or [])
            if f.get("upload_time_iso_8601") or f.get("upload_time")
        ]
        if dates:
            releases.append({"version": version, "released_at": min(dates)})
    releases.sort(key=lambda x: (_timestamp_key(x["released_at"]), x["version"]), reverse=True)
    name = info.get("name") or ""
    return {
        "summary": info.get("summary") or "Описание отсутствует в метаданных PyPI.",
        "repo": normalize_github_repo(data),
        "pypi_url": f"https://pypi.org/project/{name}/" if name else None,
        "releases": releases[:history_limit],
    }


def _timestamp_key(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0
