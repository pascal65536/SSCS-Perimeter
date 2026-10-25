"""CLI: backfill / incremental / demo. Детерминизм демо — через фиксированный ingested_at (K1-2)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEMO_INGESTED_AT = "2026-10-19T10:00:00Z"


def resolve_ingested_at(args) -> str:
    if getattr(args, "ingest_now", False):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if getattr(args, "ingested_at", None):
        from collector.ids import normalize_ts

        return normalize_ts(args.ingested_at)
    return DEMO_INGESTED_AT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="collector")
    ap.add_argument("--fixtures-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="JSON-список эталонных имён для SSCS-001",
    )
    ap.add_argument(
        "--ingest-now", action="store_true", help="реальное время приёма (K1-2)"
    )
    ap.add_argument(
        "--ingested-at", default=None, help="фиксированное время приёма (ISO 8601)"
    )
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--state", type=Path, default=None)
    args = ap.parse_args(argv)

    reference_names = (
        json.loads(args.reference.read_text(encoding="utf-8")) if args.reference else []
    )
    ingested_at = resolve_ingested_at(args)

    from collector import runner

    if args.incremental:
        state_path = args.state or (args.fixtures_dir / "state.json")
        stats = runner.run_incremental(
            state_path, args.fixtures_dir, reference_names, args.out, ingested_at
        )
    else:
        stats = runner.run_backfill(
            args.fixtures_dir, reference_names, args.out, ingested_at
        )
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "incremental" if args.incremental else "backfill",
                "ingested_at": ingested_at,
                **stats,
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_demo() -> int:
    root = Path(__file__).resolve().parent.parent / "demo_fixtures"
    reference_names = [
        "requests",
        "flask",
        "django",
        "numpy",
        "pandas",
        "sqlalchemy",
        "pytest",
        "click",
        "boto3",
        "pillow",
    ]
    out = root / "out" / "events.jsonl"
    from collector import runner

    stats = runner.run_backfill(
        root / "fixtures", reference_names, out, DEMO_INGESTED_AT
    )
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "demo",
                "ingested_at": DEMO_INGESTED_AT,
                "sha256": runner.file_sha256(out.read_text(encoding="utf-8")),
                **stats,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
