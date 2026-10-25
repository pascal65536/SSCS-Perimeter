"""Преобразование ответов API в src-пayloads для нормализаторов.

gh_payloads: (repo, package_name, commits, prs, snapshots[, members, profiles])
— переменной длины; старые 5-элементные вызовы совместимы (R2.2 обратная совместимость)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def pypi_release_payload(
    name: str,
    *,
    version: str,
    released_at: str,
    uploader: Optional[str],
    size: Optional[int],
    yanked: bool,
    requires_dist: List[str],
    sha256: Optional[str],
) -> Dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "released_at": released_at,
        "uploader": uploader,
        "size": size,
        "yanked": yanked,
        "requires_dist": requires_dist,
        "sha256": sha256,
    }


def pypi_created_payload(
    name: str,
    *,
    first_release_at: str,
    uploader: Optional[str],
    levenshtein_hits: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "first_release_at": first_release_at,
        "uploader": uploader,
        "levenshtein_hits": levenshtein_hits or [],
    }


def gh_payloads(
    repo: str,
    package_name: Optional[str],
    commits: List[Dict[str, Any]],
    prs: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    members: Optional[List[Dict[str, Any]]] = None,
    profiles: Optional[List[Dict[str, Any]]] = None,
):
    entry: Tuple = (repo, package_name, commits, prs, snapshots)
    if members is not None or profiles is not None:
        entry = entry + (members or [], profiles or [])
    return entry
