import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

PYPI_JSON = "https://pypi.org/pypi/{name}/json"
DELAY = 0.3
TIMEOUT = 30
UA = {"User-Agent": "sscs-monitor/0.1 (diploma research; pilot)"}
LIMIT = int(os.environ.get("LIMIT", "0"))  # 0 = без ограничения

GROUND_TRUTH = [
    "colourama",
    "jeilyfish",
    "python3-dateutil",
    "ctx",
    "torchtriton",
    "ultralytics",
]


def fetch_one(name: str):
    req = urllib.request.Request(PYPI_JSON.format(name=name), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return f"error:{type(e).__name__}", None


def to_fixture(name: str, data: dict, watchlist: str):
    info = data.get("info") or {}
    releases = {}
    for ver, files in (data.get("releases") or {}).items():
        releases[ver] = [
            {
                "upload_time": f["upload_time_iso_8601"],
                "size": f.get("size"),
                "yanked": bool(f.get("yanked")),
                "digests": {"sha256": (f.get("digests") or {}).get("sha256")},
            }
            for f in (files or [])
            if f.get("upload_time_iso_8601")
        ]
    releases = {v: fs for v, fs in releases.items() if fs}
    if not releases:
        return None
    latest = max(releases, key=lambda v: max(f["upload_time"] for f in releases[v]))
    return {
        "kind": "pypi_package",
        "watchlist": watchlist,
        "repo": None,
        "info": {
            "name": name,
            "version": latest,
            "uploader": info.get("maintainer_email") or None,
            "requires_dist": info.get("requires_dist") or [],
        },
        "releases": releases,
    }


def main():
    pilot = Path("pilot")
    fx_dir = pilot / "pypi_fixtures"
    fx_dir.mkdir(parents=True, exist_ok=True)
    ref_names = json.loads((pilot / "reference.json").read_text(encoding="utf-8"))
    watchlist_of = {n: "reference" for n in ref_names}
    for n in GROUND_TRUTH:
        watchlist_of.setdefault(n, "ground_truth")

    names = sorted(watchlist_of)
    if LIMIT:
        names = names[:LIMIT]
    total = len(names)

    stats = {"fetched": 0, "resumed": 0, "empty": [], "missing_404": [], "errors": []}
    t0 = time.time()
    for i, name in enumerate(names, 1):
        path = fx_dir / f"{name}.json"
        if path.exists():  # resume: пропуск уже скачанного
            stats["resumed"] += 1
        else:
            status, data = fetch_one(name)
            if status == 200:
                fixture = to_fixture(name, data, watchlist_of[name])
                if fixture is None:
                    stats["empty"].append(name)
                else:
                    path.write_text(
                        json.dumps(fixture, ensure_ascii=False), encoding="utf-8"
                    )
                    stats["fetched"] += 1
            elif status == 404:
                stats["missing_404"].append(name)
            else:
                stats["errors"].append({"name": name, "status": status})
            time.sleep(DELAY)

        if i % 10 == 0 or i == total:
            elapsed = time.time() - t0
            eta = elapsed / i * (total - i)
            print(
                f"[{i}/{total}] {name:30s} elapsed {elapsed:6.1f}s "
                f"eta {eta:6.1f}s fetched {stats['fetched']} "
                f"404 {len(stats['missing_404'])}",
                flush=True,
            )

    (pilot / "fetched_report.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in stats.items()}
    summary["total"] = total
    print("ИТОГ:", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
