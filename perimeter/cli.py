from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from settings_manager import SettingsManager

from .builder import PerimeterBuilder
from .lockfile import read_lockfile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-perimeter")
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    parser.add_argument("--project", default=None, help="Имя проекта при добавлении roots")
    parser.add_argument("--root", action="append", default=[], help="name или name==version")
    parser.add_argument("--lockfile", type=Path)
    parser.add_argument("--generated-at", help="Фиксированный UTC timestamp для воспроизводимого запуска")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    manager = SettingsManager(args.settings)
    if args.lockfile:
        roots = read_lockfile(args.lockfile)
        project_name = args.project or args.lockfile.stem
    elif args.root:
        roots = []
        for value in args.root:
            name, sep, version = value.partition("==")
            roots.append({"name": name, "version": version if sep else None})
        project_name = args.project or "my-project"
    else:
        settings = manager.load()
        roots = settings["project"]["roots"]
        project_name = settings["project"]["name"]

    result = PerimeterBuilder(max_workers=args.max_workers).build(roots, project_name=project_name)
    stamp = args.generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.dry_run:
        if args.settings.exists():
            current = manager.load()
            if args.root or args.lockfile:
                current["project"] = {"name": project_name, "roots": roots}
                manager.save(current)
        else:
            data = manager.load_or_default(project_name)
            data["project"] = {"name": project_name, "roots": roots}
            manager.save(data)
        manager.replace_perimeter(result.packages, stamp)
    print(json.dumps(result.as_dict(stamp), ensure_ascii=False, sort_keys=True))
    return 0 if result.packages else 2


if __name__ == "__main__":
    sys.exit(main())
