from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .gateway import OpenSearchGateway

CONTENT = Path(__file__).with_name("content")


def content_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in CONTENT.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(CONTENT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-siem-provision")
    parser.add_argument("--url", default="https://localhost:9200")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--apply-ml", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    operations = [
        ("PUT", "/_index_template/sscs-events", CONTENT / "index-template.json"),
        ("PUT", "/_plugins/_ism/policies/sscs-retention-18m", CONTENT / "ism-policy.json"),
    ]
    if args.apply_ml:
        operations.extend([
            ("POST", "/_plugins/_anomaly_detection/detectors", CONTENT / "ml-sscs-002.json"),
            ("POST", "/_plugins/_anomaly_detection/detectors", CONTENT / "ml-sscs-005.json"),
        ])
    print(json.dumps({"detector_config_hash": content_hash(), "operations": len(operations), "dry_run": args.dry_run}))
    if args.dry_run:
        return 0
    gateway = OpenSearchGateway(args.url, verify_tls=not args.insecure)
    for method, path, file in operations:
        body = file.read_bytes()
        gateway._request(method, path, body, "application/json")
        print(f"OK {method} {path}")
    print("Sigma/correlation content импортируется через Security Analytics; см. docs/SIEM.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
