from __future__ import annotations

from typing import Any, Dict, List, Optional


def collect_repo_commit(fixture: Dict[str, Any]) -> Dict[str, Any]:
    c = fixture["commit"]
    return {
        "repo": fixture["repo"],
        "sha": c["sha"],
        "login": c.get("login"),
        "message": c.get("message"),
        "additions": c.get("additions"),
        "deletions": c.get("deletions"),
        "files_changed": c.get("files_changed"),
        "is_merge": bool(c.get("is_merge")),
        "anonymous": not c.get("login"),
        "committed_at": c["committed_at"],
        "package_name": fixture.get("package_name"),
    }


def collect_repo_pull_request(fixture: Dict[str, Any]) -> Dict[str, Any]:
    pr = fixture["pull_request"]
    return {
        "repo": fixture["repo"],
        "number": pr["number"],
        "author": pr.get("author"),
        "package_name": fixture.get("package_name"),
        "created_at": pr["created_at"],
        "merged_at": pr.get("merged_at"),
        "merged_by": pr.get("merged_by"),
        "review_count": pr.get("review_count"),
        "touches_critical": bool(pr.get("touches_critical")),
        "author_first_contrib_at": pr.get("author_first_contrib_at"),
        "author_account_created_at": pr.get("author_account_created_at"),
    }


def collect_repo_snapshot(fixture: Dict[str, Any]) -> Dict[str, Any]:
    s = fixture["snapshot"]
    return {
        "repo": fixture["repo"],
        "date": s["date"],
        "stars": s.get("stars"),
        "forks": s.get("forks"),
        "watchers": s.get("watchers"),
        "open_issues": s.get("open_issues"),
        "open_prs": s.get("open_prs"),
    }


def collect_repo_membership_change(fixture: Dict[str, Any]) -> Dict[str, Any]:
    m = fixture["membership"]
    return {
        "repo": fixture["repo"],
        "login": m["login"],
        "role": m.get("role", "maintainer"),
        "change_type": m["change_type"],
        "event_at": m["event_at"],
        "package_name": fixture.get("package_name"),
    }


def collect_user_profile_snapshot(fixture: Dict[str, Any]) -> Dict[str, Any]:
    p = fixture["profile"]
    return {
        "login": p["login"],
        "date": p["date"],
        "account_created_at": p.get("account_created_at"),
        "followers": p.get("followers"),
        "public_repos": p.get("public_repos"),
    }
