"""Режимы backfill/incremental; паузы rate limit — только через ratelimit.handle_status (K1-3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from collector import ids, normalize, payloads, ratelimit, state as state_mod
from collector.collectors import github as gh
from collector.collectors import pypi as py


def canonical_jsonl(docs: List[dict]) -> str:
    lines = [
        json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for d in docs
    ]
    lines.sort()
    return "".join(ln + "\n" for ln in lines)


def file_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_backfill(
    fixtures_dir: Path,
    reference_names: List[str],
    out_path: Path,
    ingested_at: str,
    ratelimit_state: Optional[ratelimit.RateLimitState] = None,
) -> Dict[str, int]:
    rl = ratelimit_state or ratelimit.RateLimitState(simulated=True)
    docs: List[dict] = []
    for fx in sorted(fixtures_dir.glob("*.json")):
        fixture = _load_fixture(fx)
        kind = fixture.get("kind")
        watchlist = fixture.get("watchlist", "monitored")
        repo = fixture.get("repo")
        if kind == "pypi_package":
            name = fixture["info"]["name"]
            docs.append(
                normalize.normalize_pypi_created(
                    py.collect_pypi_created(fixture, reference_names),
                    watchlist=watchlist,
                    repo=repo,
                    ingested_at=ingested_at,
                )
            )
            for ver, files in (fixture.get("releases") or {}).items():
                if not files:
                    continue
                f0 = sorted(files, key=lambda f: f.get("upload_time") or "")[0]
                docs.append(
                    normalize.normalize_pypi_release(
                        {
                            "name": name,
                            "version": ver,
                            "released_at": f0["upload_time"],
                            "uploader": fixture["info"].get("uploader"),
                            "size": f0.get("size"),
                            "yanked": bool(f0.get("yanked")),
                            "requires_dist": fixture["info"].get("requires_dist") or [],
                            "sha256": (f0.get("digests") or {}).get("sha256"),
                        },
                        watchlist=watchlist,
                        repo=repo,
                        ingested_at=ingested_at,
                    )
                )
        elif kind == "github_repo":
            rl.sleep(
                0
            )  # единая точка учёта квоты; реальные вызовы — через handle_status
            for cfx in fixture.get("commits") or []:
                docs.append(
                    normalize.normalize_github_commit(
                        gh.collect_repo_commit(
                            {
                                "repo": repo,
                                "package_name": fixture.get("package_name"),
                                "commit": cfx,
                            }
                        ),
                        watchlist=watchlist,
                        ingested_at=ingested_at,
                    )
                )
            for prfx in fixture.get("pull_requests") or []:
                docs.append(
                    normalize.normalize_github_pr(
                        gh.collect_repo_pull_request(
                            {
                                "repo": repo,
                                "package_name": fixture.get("package_name"),
                                "pull_request": prfx,
                            }
                        ),
                        watchlist=watchlist,
                        ingested_at=ingested_at,
                    )
                )
            for sfx in fixture.get("snapshots") or []:
                docs.append(
                    normalize.normalize_repo_snapshot(
                        gh.collect_repo_snapshot({"repo": repo, "snapshot": sfx}),
                        watchlist=watchlist,
                        ingested_at=ingested_at,
                    )
                )
            for mfx in fixture.get("members") or []:
                docs.append(
                    normalize.normalize_membership_change(
                        gh.collect_repo_membership_change(
                            {
                                "repo": repo,
                                "package_name": fixture.get("package_name"),
                                "membership": mfx,
                            }
                        ),
                        watchlist=watchlist,
                        ingested_at=ingested_at,
                    )
                )
            profiles = fixture.get("profiles")
            if profiles:
                for pfx in profiles:
                    docs.append(
                        normalize.normalize_user_profile_snapshot(
                            gh.collect_user_profile_snapshot({"profile": pfx}),
                            watchlist=watchlist,
                            ingested_at=ingested_at,
                        )
                    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(canonical_jsonl(docs), encoding="utf-8")
    return {"events": len(docs)}


def run_incremental(
    state_path: Path,
    fixtures_dir: Path,
    reference_names: List[str],
    out_path: Path,
    ingested_at: str,
    ratelimit_state: Optional[ratelimit.RateLimitState] = None,
) -> Dict[str, int]:
    rl = ratelimit_state or ratelimit.RateLimitState(simulated=True)
    state = state_mod.load(state_path)
    tmp_out = out_path.with_suffix(".tmp")
    stats = run_backfill(fixtures_dir, reference_names, tmp_out, ingested_at, rl)
    new_docs: List[dict] = []
    for line in tmp_out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        rl.sleep(0)
        if doc["event"]["id"] not in state.last_seen_event_ids:
            new_docs.append(doc)
    out_path.write_text(canonical_jsonl(new_docs), encoding="utf-8")
    state_mod.save(
        state_path,
        state_mod.make_state(
            [d["event"]["id"] for d in new_docs] + state.last_seen_event_ids,
            ingested_at,
        ),
    )
    tmp_out.unlink(missing_ok=True)
    return {"events": len(new_docs)}
