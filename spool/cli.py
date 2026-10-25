from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from siem import OpenSearchGateway

from .queue import DiskSpool


def iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-spool")
    parser.add_argument("--directory", type=Path, default=Path(".sscs/spool"))
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("input", type=Path)
    sub.add_parser("status")
    deliver = sub.add_parser("deliver")
    deliver.add_argument("--url", default="https://localhost:9200")
    deliver.add_argument("--index", default="sscs-events")
    deliver.add_argument("--insecure", action="store_true")
    args = parser.parse_args(argv)
    spool = DiskSpool(args.directory, max_bytes=args.max_bytes)
    if args.command == "ingest":
        result = spool.extend(iter_jsonl(args.input))
    elif args.command == "deliver":
        gateway = OpenSearchGateway(args.url, index=args.index, verify_tls=not args.insecure)
        result = spool.deliver(gateway)
    else:
        result = {"queued": spool.count, "bytes": spool.size_bytes}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
