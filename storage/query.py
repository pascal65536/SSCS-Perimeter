_VIEWS = {
    "v_releases": "SELECT * FROM releases WHERE released_at <= ?",
    "v_commits": "SELECT * FROM commits WHERE committed_at <= ?",
    "v_pull_requests": "SELECT * FROM pull_requests WHERE created_at <= ?",
    "v_repo_snapshots": "SELECT * FROM repo_snapshots WHERE date <= ?",
    "v_maintainer_edges": "SELECT * FROM membership_events WHERE event_at <= ?",
}


def get_as_of(conn, view, t_iso):
    if view not in _VIEWS:
        raise ValueError(f"unknown PIT view: {view}")
    return conn.execute(_VIEWS[view], (t_iso,)).fetchall()
