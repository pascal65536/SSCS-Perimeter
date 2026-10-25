from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from settings_manager import SettingsManager
from spool import DiskSpool

from .live import PerimeterCollector


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-collector-live")
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    parser.add_argument("--state", type=Path, default=Path(".sscs/collector-state.json"))
    parser.add_argument("--spool", type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ingested-at", help="Фиксированное время для воспроизводимого теста")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = SettingsManager(args.settings).load()
    spool = DiskSpool(args.spool or settings["spool"]["path"], max_bytes=settings["spool"]["max_bytes"])
    collector = PerimeterCollector(settings, spool, args.state)
    while True:
        result = collector.run_once(ingested_at=args.ingested_at)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        if args.once:
            return 0
        time.sleep(settings["polling"]["pypi_seconds"])


if __name__ == "__main__":
    sys.exit(main())
