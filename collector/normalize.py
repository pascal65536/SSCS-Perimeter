"""Нормализация сырых ответов API в JSON-конверт sscs-event/1.0 (Приложение А.1)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector import ids

SCHEMA_VERSION = "1.0"


def _is_new_contributor(created_at: str, first_contrib_at: str | None) -> bool:
    if not first_contrib_at:
        return False
    from datetime import datetime, timedelta
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    first = datetime.fromisoformat(ids.normalize_ts(first_contrib_at).replace("Z", "+00:00"))
    return timedelta(0) <= created - first <= timedelta(days=30)


def with_perimeter_root(event: Dict[str, Any], roots: List[str]) -> Dict[str, Any]:
    """Маршрутизация владельцам проектов без изменения детерминированного event.id."""
    event["sscs"]["perimeter_root"] = sorted(set(roots))
    return event


def _envelope(
    *,
    event_id: str,
    kind: str,
    category: str,
    type_: str,
    action: str,
    ingested_at: str,
    source_service: str,
    component: str,
    package: Optional[Dict],
    user: Optional[Dict],
    watchlist: str,
    repo: Optional[str],
    sscs_extra: Dict[str, Any],
) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "@timestamp": sscs_extra.pop("_ts"),
        "event": {
            "id": event_id,
            "kind": kind,
            "category": category,
            "type": type_,
            "action": action,
            "ingested": ingested_at,
            "outcome": "success",
        },
        "source": {"service": source_service, "component": component},
        "sscs": {
            "schema_version": SCHEMA_VERSION,
            "watchlist": watchlist,
            "repo": repo,
            "point_in_time": True,
            "perimeter_root": [],
        },
    }
    if package is not None:
        doc["package"] = package
    if user is not None:
        doc["user"] = user
    doc["sscs"].update(sscs_extra)
    return doc


def normalize_pypi_release(
    src: Dict[str, Any], *, watchlist: str, repo: Optional[str], ingested_at: str
) -> Dict[str, Any]:
    """src: {"name","version","released_at","uploader","size","yanked","requires_dist","sha256"}"""
    released_at = ids.normalize_ts(src["released_at"])
    return _envelope(
        event_id=ids.release_id(src["name"], src["version"], released_at),
        kind="event",
        category="package",
        type_="creation",
        action="package.release",
        ingested_at=ingested_at,
        source_service="pypi-api",
        component="pypi-json",
        package={
            "name": ids.normalize_id(src["name"]),
            "version": src["version"],
            "registry": "pypi",
            "author": src.get("uploader"),
        },
        user=None,
        watchlist=watchlist,
        repo=repo,
        sscs_extra={
            "_ts": released_at,
            "release": {
                "released_at": released_at,
                "size": src.get("size"),
                "yanked": bool(src.get("yanked")),
                "requires_dist": src.get("requires_dist") or [],
                "digests": {"sha256": src.get("sha256")},
            },
        },
    )


def normalize_pypi_created(
    src: Dict[str, Any], *, watchlist: str, repo: Optional[str], ingested_at: str
) -> Dict[str, Any]:
    """src: {"name","first_release_at","uploader","levenshtein_hits"}"""
    first = ids.normalize_ts(src["first_release_at"])
    return _envelope(
        event_id=ids.created_id(src["name"], first),
        kind="event",
        category="package",
        type_="creation",
        action="package.created",
        ingested_at=ingested_at,
        source_service="pypi-api",
        component="pypi-json",
        package={
            "name": ids.normalize_id(src["name"]),
            "registry": "pypi",
            "author": src.get("uploader"),
        },
        user=None,
        watchlist=watchlist,
        repo=repo,
        sscs_extra={
            "_ts": first,
            "reference": watchlist == "reference",
            "created": {
                "first_release_at": first,
                "levenshtein_hits": src.get("levenshtein_hits") or [],
            },
        },
    )


def normalize_github_commit(
    src: Dict[str, Any], *, watchlist: str, ingested_at: str
) -> Dict[str, Any]:
    """src: {"repo","sha","login","message","additions","deletions","files_changed","is_merge","anonymous","committed_at"}"""
    committed_at = ids.normalize_ts(src["committed_at"])
    return _envelope(
        event_id=ids.commit_id(src["repo"], src["sha"]),
        kind="event",
        category="code_change",
        type_="change",
        action="repo.commit",
        ingested_at=ingested_at,
        source_service="github-api",
        component="github-rest",
        package={"name": src.get("package_name"), "registry": None, "author": None},
        user={"name": src.get("login")},
        watchlist=watchlist,
        repo=src["repo"],
        sscs_extra={
            "_ts": committed_at,
            "commit": {
                "sha": src["sha"].lower(),
                "message": (src.get("message") or "")[:120],
                "additions": src.get("additions"),
                "deletions": src.get("deletions"),
                "files_changed": src.get("files_changed"),
                "is_merge": bool(src.get("is_merge")),
                "anonymous": bool(src.get("anonymous")),
                "committed_at": committed_at,
                "hour_of_day": int(committed_at[11:13]),
            },
        },
    )


def normalize_github_pr(
    src: Dict[str, Any], *, watchlist: str, ingested_at: str
) -> Dict[str, Any]:
    """src: {"repo","number","author","package_name","created_at","merged_at","merged_by","review_count","touches_critical","author_first_contrib_at"}"""
    created_at = ids.normalize_ts(src["created_at"])
    return _envelope(
        event_id=ids.pr_id(src["repo"], src["number"]),
        kind="event",
        category="code_change",
        type_="change",
        action="repo.pull_request",
        ingested_at=ingested_at,
        source_service="github-api",
        component="github-rest",
        package={"name": src.get("package_name"), "registry": None, "author": None},
        user={"name": src.get("author")},
        watchlist=watchlist,
        repo=src["repo"],
        sscs_extra={
            "_ts": created_at,
            "pr": {
                "number": src["number"],
                "created_at": created_at,
                "merged_at": src.get("merged_at")
                and ids.normalize_ts(src["merged_at"]),
                "merged_by": src.get("merged_by"),
                "review_count": src.get("review_count"),
                "touches_critical": bool(src.get("touches_critical")),
                "author_first_contrib_at": src.get("author_first_contrib_at"),
                "author_account_created_at": src.get("author_account_created_at"),
                "author_is_new": _is_new_contributor(created_at, src.get("author_first_contrib_at")),
                "self_merge": bool(src.get("author") and src.get("author") == src.get("merged_by")),
            },
        },
    )


def normalize_repo_snapshot(
    src: Dict[str, Any], *, watchlist: str, ingested_at: str
) -> Dict[str, Any]:
    """src: {"repo","date","stars","forks","watchers","open_issues","open_prs"}"""
    return _envelope(
        event_id=ids.repo_snapshot_id(src["repo"], src["date"]),
        kind="metric",
        category="process",
        type_="info",
        action="repo.snapshot",
        ingested_at=ingested_at,
        source_service="github-api",
        component="github-rest",
        package=None,
        user=None,
        watchlist=watchlist,
        repo=src["repo"],
        sscs_extra={
            "_ts": f"{src['date']}T00:00:00Z",
            "repo_snapshot": {
                "date": src["date"],
                "stars": src.get("stars"),
                "forks": src.get("forks"),
                "watchers": src.get("watchers"),
                "open_issues": src.get("open_issues"),
                "open_prs": src.get("open_prs"),
            },
        },
    )


def normalize_user_profile_snapshot(
    src: Dict[str, Any], *, watchlist: str, ingested_at: str
) -> Dict[str, Any]:
    """src: {"login","account_created_at","followers","public_repos","date"}"""
    return _envelope(
        event_id=ids.user_profile_id(src["login"], src["date"]),
        kind="metric",
        category="user",
        type_="info",
        action="user.profile_snapshot",
        ingested_at=ingested_at,
        source_service="github-api",
        component="github-rest",
        package=None,
        user={"name": ids.normalize_id(src["login"])},
        watchlist=watchlist,
        repo=None,
        sscs_extra={
            "_ts": f"{src['date']}T00:00:00Z",
            "user": {
                "account_created_at": src.get("account_created_at")
                and ids.normalize_ts(src["account_created_at"]),
                "followers": src.get("followers"),
                "public_repos": src.get("public_repos"),
            },
        },
    )


def normalize_membership_change(
    src: Dict[str, Any], *, watchlist: str, ingested_at: str
) -> Dict[str, Any]:
    """src: {"repo","login","role","change_type","event_at","package_name"}"""
    event_at = ids.normalize_ts(src["event_at"])
    change_type = str(src["change_type"]).strip().lower()
    if change_type not in ("added", "removed"):
        raise ValueError(f"unknown change_type: {change_type!r}")
    return _envelope(
        event_id=ids.membership_id(src["repo"], src["login"], event_at, change_type),
        kind="event",
        category="iam",
        type_="creation" if change_type == "added" else "deletion",
        action="repo.membership_change",
        ingested_at=ingested_at,
        source_service="github-api",
        component="github-rest",
        package={"name": src.get("package_name"), "registry": None, "author": None},
        user={"name": ids.normalize_id(src["login"])},
        watchlist=watchlist,
        repo=src["repo"],
        sscs_extra={
            "_ts": event_at,
            "member": {
                "login": ids.normalize_id(src["login"]),
                "role": src.get("role", "maintainer"),
                "event_at": event_at,
                "change_type": change_type,
            },
        },
    )
