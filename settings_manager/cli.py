from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manager import SettingsManager


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-settings")
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project", default="my-project")
    init.add_argument("--force", action="store_true")
    add = sub.add_parser("add-root")
    add.add_argument("name")
    add.add_argument("--version")
    sub.add_parser("validate")
    args = parser.parse_args(argv)
    manager = SettingsManager(args.settings)
    if args.command == "init":
        data = manager.initialize(args.project, force=args.force)
    elif args.command == "add-root":
        data = manager.add_root(args.name, args.version)
    else:
        data = manager.load()
    print(json.dumps({"ok": True, "settings": str(manager.path), "roots": len(data["project"]["roots"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
