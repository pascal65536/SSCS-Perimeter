from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _parse_iso_z(s: str) -> str:
    if not isinstance(s, str) or len(s) < 20:
        raise ValueError(f"bad ISO timestamp: {s!r}")
    if not (s.endswith("Z") or s.endswith("+00:00")):
        raise ValueError(f"timestamp must be UTC: {s!r}")
    return s


_TIME_FALLBACK = {
    "package.release": ["sscs.release.released_at", "@timestamp"],
    "package.created": ["sscs.created.first_release_at", "@timestamp"],
    "repo.commit": ["sscs.commit.committed_at", "@timestamp"],
    "repo.pull_request": ["sscs.pr.created_at", "@timestamp"],
    "repo.membership_change": ["sscs.member.event_at", "@timestamp"],
    "user.profile_snapshot": ["sscs.user.snapshot_at", "@timestamp"],
    "repo.snapshot": ["sscs.repo_snapshot.date", "@timestamp"],
}


def _dig(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, str) and cur else None


def _normalize_event_time(doc):
    action = doc.get("event", {}).get("action", "")
    raw = doc.get("@timestamp")
    if isinstance(raw, str) and raw:
        return _parse_iso_z(raw)
    for path in _TIME_FALLBACK.get(action, ["@timestamp"]):
        v = _dig(doc, path)
        if v:
            return _parse_iso_z(v)
    raise ValueError(
        f"R3 violation: '@timestamp' is null and no fallback for action={action!r}"
    )


def upsert_package(
    conn, *, name, registry, watchlist, github_repo, is_reference, first_seen, now
):
    row = conn.execute(
        "SELECT id, last_seen FROM packages WHERE name=?", (name,)
    ).fetchone()
    if row:
        pkg_id, prev = row
        conn.execute(
            """UPDATE packages SET registry=?, watchlist=?, github_repo=?,
                        is_reference=?, last_seen=? WHERE id=?""",
            (
                registry,
                watchlist,
                github_repo,
                int(is_reference),
                max(prev, now),
                pkg_id,
            ),
        )
        return pkg_id
    cur = conn.execute(
        """INSERT INTO packages
        (name, registry, watchlist, github_repo, is_reference, first_seen, last_seen)
        VALUES (?,?,?,?,?,?,?)""",
        (name, registry, watchlist, github_repo, int(is_reference), first_seen, now),
    )
    return int(cur.lastrowid)


def _insert_ingest_log(conn, doc, received_at):
    ev = doc["event"]
    conn.execute(
        """INSERT INTO ingest_log
        (event_id, ingested_at, source_service, outcome, schema_version)
        VALUES (?,?,?,?,?)""",
        (
            ev["id"],
            received_at,
            doc["source"]["service"],
            ev["outcome"],
            doc["sscs"]["schema_version"],
        ),
    )


def _resolve_package_id(conn, doc, received_at):
    pkg = doc.get("package") or {}
    name = _normalize_name(pkg.get("name", ""))
    if not name:
        raise ValueError("package.name required for package.* events")
    row = conn.execute("SELECT id FROM packages WHERE name=?", (name,)).fetchone()
    if row:
        conn.execute(
            "UPDATE packages SET last_seen=? WHERE id=?", (received_at, row[0])
        )
        return int(row[0])
    return upsert_package(
        conn,
        name=name,
        registry=pkg.get("registry", "pypi"),
        watchlist=doc["sscs"]["watchlist"],
        github_repo=doc["sscs"].get("repo"),
        is_reference=1 if doc["sscs"]["watchlist"] == "reference" else 0,
        first_seen=received_at,
        now=received_at,
    )


def _insert_package_release(conn, doc, received_at):
    pkg_id = _resolve_package_id(conn, doc, received_at)
    p, s = doc["package"], doc["sscs"]["release"]
    conn.execute(
        """INSERT INTO releases
        (event_id, package_id, version, released_at, uploader, size, yanked, sha256)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            doc["event"]["id"],
            pkg_id,
            p["version"],
            s["released_at"],
            p.get("author"),
            s.get("size"),
            1 if s.get("yanked") else 0,
            (s.get("digests") or {}).get("sha256"),
        ),
    )


def _insert_package_created(conn, doc, received_at):
    p, s = doc["package"], doc["sscs"]
    upsert_package(
        conn,
        name=_normalize_name(p["name"]),
        registry=p.get("registry", "pypi"),
        watchlist=s["watchlist"],
        github_repo=s.get("repo"),
        is_reference=1 if s["watchlist"] == "reference" else 0,
        first_seen=s["created"]["first_release_at"],
        now=received_at,
    )


def _insert_repo_commit(conn, doc, received_at):
    c = doc["sscs"]["commit"]
    conn.execute(
        """INSERT INTO commits
        (event_id, repo, sha, author_login, committed_at, additions, deletions,
         files_changed, is_merge, is_anonymous)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            doc["event"]["id"],
            doc["sscs"]["repo"],
            c["sha"],
            (doc.get("user") or {}).get("name"),
            c.get("committed_at") or _normalize_event_time(doc),
            c.get("additions"),
            c.get("deletions"),
            c.get("files_changed"),
            1 if c.get("is_merge") else 0,
            1 if c.get("anonymous") else 0,
        ),
    )


def _insert_repo_membership_change(conn, doc, received_at):
    m = doc["sscs"]["member"]
    change_type = "added" if doc["event"].get("type") == "creation" else "removed"
    conn.execute(
        """INSERT INTO membership_events
        (event_id, repo, login, change_type, role, event_at) VALUES (?,?,?,?,?,?)""",
        (
            doc["event"]["id"],
            doc["sscs"]["repo"],
            m["login"],
            change_type,
            m.get("role", "maintainer"),
            m["event_at"],
        ),
    )


def _insert_user_profile_snapshot(conn, doc, received_at):
    u = doc["sscs"]["user"]
    login = doc["user"]["name"].strip().lower()  # ПАТЧ S-2
    conn.execute(
        """INSERT INTO user_profiles
        (login, account_created_at, followers, public_repos, snapshot_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(login) DO UPDATE SET
            account_created_at=excluded.account_created_at,
            followers=excluded.followers,
            public_repos=excluded.public_repos,
            snapshot_at=excluded.snapshot_at""",
        (
            login,
            u["account_created_at"],
            u.get("followers"),
            u.get("public_repos"),
            u.get("snapshot_at") or _normalize_event_time(doc),
        ),
    )


def _insert_repo_pull_request(conn, doc, received_at):
    pr = doc["sscs"]["pr"]
    conn.execute(
        """INSERT INTO pull_requests
        (event_id, repo, number, author, created_at, merged_at, merged_by,
         review_count, touches_critical, author_first_contrib_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            doc["event"]["id"],
            doc["sscs"]["repo"],
            pr["number"],
            (doc.get("user") or {}).get("name"),
            pr["created_at"],
            pr.get("merged_at"),
            pr.get("merged_by"),
            pr.get("review_count"),
            1 if pr.get("touches_critical") else 0,
            pr.get("author_first_contrib_at"),
        ),
    )


def _insert_repo_snapshot(conn, doc, received_at):
    s = doc["sscs"]["repo_snapshot"]
    conn.execute(
        """INSERT INTO repo_snapshots
        (event_id, repo, date, stars, forks, watchers, open_issues, open_prs)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            doc["event"]["id"],
            doc["sscs"]["repo"],
            s["date"],
            s.get("stars"),
            s.get("forks"),
            s.get("watchers"),
            s.get("open_issues"),
            s.get("open_prs"),
        ),
    )


_ROUTES = {
    "package.release": _insert_package_release,
    "package.created": _insert_package_created,
    "repo.commit": _insert_repo_commit,
    "repo.membership_change": _insert_repo_membership_change,
    "user.profile_snapshot": _insert_user_profile_snapshot,
    "repo.pull_request": _insert_repo_pull_request,
    "repo.snapshot": _insert_repo_snapshot,
}


def _insert_document(conn, doc, received_at):
    action = doc["event"]["action"]
    if action not in _ROUTES:
        raise ValueError(f"unknown event.action: {action!r}")
    _insert_ingest_log(conn, doc, received_at)
    _ROUTES[action](conn, doc, received_at)


def _event_time_for_check(doc, event_time):
    action = doc["event"]["action"]
    m = {
        "package.release": ("sscs", "release", "released_at"),
        "repo.commit": ("sscs", "commit", "committed_at"),
        "repo.membership_change": ("sscs", "member", "event_at"),
    }
    if action in m:
        a, b, c = m[action]
        v = (doc.get(a) or {}).get(b, {}).get(c)
        if v:
            return v
    return event_time


def ingest_jsonl(conn, path):
    if conn.in_transaction:
        raise RuntimeError(
            "ingest_jsonl() must be called outside an active transaction"
        )
    accepted = duplicates = errors = 0
    details = []
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    conn.execute("BEGIN IMMEDIATE")
    try:
        for lineno, line in enumerate(lines, 1):
            try:
                doc = json.loads(line)
                eid = doc["event"]["id"]
                if conn.execute(
                    "SELECT 1 FROM ingest_log WHERE event_id=?", (eid,)
                ).fetchone():
                    duplicates += 1
                    continue
                event_time = _normalize_event_time(doc)  # время события
                received_at = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )  # ПАТЧ S-1
                if _event_time_for_check(doc, event_time) > received_at:
                    raise ValueError("PIT violation: event time > received_at")
                _insert_document(conn, doc, received_at)
                accepted += 1
            except Exception as exc:
                errors += 1
                details.append({"line": lineno, "error": str(exc)})
                raise
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "errors": errors,
        "error_details": details,
    }
