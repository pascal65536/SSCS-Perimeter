from __future__ import annotations

from typing import Any, Dict, List, Optional


def collect_pypi_release(fixture: Dict[str, Any]) -> Dict[str, Any]:
    info = fixture["info"]
    releases = fixture.get("releases") or {}
    version = info["version"]
    files = releases.get(version) or []
    if not files:
        raise ValueError(f"no files for version {version!r}")
    f0 = sorted(files, key=lambda f: f.get("upload_time") or "")[0]
    return {
        "name": info["name"],
        "version": version,
        "released_at": f0["upload_time"],
        "uploader": info.get("uploader"),
        "size": f0.get("size"),
        "yanked": bool(f0.get("yanked")),
        "requires_dist": (fixture.get("info") or {}).get("requires_dist") or [],
        "sha256": (f0.get("digests") or {}).get("sha256"),
    }


def collect_pypi_created(
    fixture: Dict[str, Any], reference_names: List[str]
) -> Dict[str, Any]:
    info = fixture["info"]
    releases = fixture.get("releases") or {}
    times = sorted(
        f["upload_time"]
        for files in releases.values()
        for f in files
        if f.get("upload_time")
    )
    if not times:
        raise ValueError("no release times")
    from collector.detectors_util import levenshtein  # локальная копия

    name = info["name"]
    hits = []
    for ref in reference_names:
        if ref == name:
            continue
        d = levenshtein(name, ref)
        if 0 < d <= 2:
            hits.append({"name": ref, "distance": d})
    hits.sort(key=lambda h: h["distance"])
    return {
        "name": name,
        "first_release_at": times[0],
        "uploader": info.get("uploader"),
        "levenshtein_hits": hits[:5],
    }
