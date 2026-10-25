from __future__ import annotations

import argparse
import json
import sys
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

from collector import normalize
from collector.collectors import pypi as py
from collector.live import PyPIPoller
from collector.state import load, make_state, save
from spool import DiskSpool


class ChangelogUnavailable(RuntimeError):
    pass


def changelog_proxy(url: str = "https://pypi.org/pypi", timeout: int = 20):
    # Транспорт создаётся на каждый запуск: доступность проверяется до этапа 3.
    proxy = xmlrpc.client.ServerProxy(url, allow_none=True)
    proxy._ServerProxy__transport.timeout = timeout
    return proxy


class GlobalPyPICollector:
    """Инкрементальный XML-RPC Changelog; cursor=serial, без глобального архива."""

    def __init__(self, spool: DiskSpool, state_path: str | Path, reference: list[str], *, proxy=None, pypi=None):
        self.spool = spool
        self.state_path = Path(state_path)
        self.reference = reference
        self.proxy = proxy or changelog_proxy()
        self.pypi = pypi or PyPIPoller()

    def check(self) -> bool:
        try:
            serial = int(self.proxy.changelog_last_serial())
            return serial >= 0
        except (OSError, xmlrpc.client.Error) as exc:
            raise ChangelogUnavailable(
                "XML-RPC Changelog недоступен. Используйте perimeter polling; для глобальной статистики подключите BigQuery."
            ) from exc

    def run_once(self, *, limit: int = 1000) -> dict:
        self.check()
        state = load(self.state_path)
        serial = int(state.next_cursor or 0)
        entries = sorted(self.proxy.changelog_since_serial(serial), key=lambda row: row[4])[:limit]
        accepted = 0
        for name, version, timestamp, action, entry_serial in entries:
            stamp = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if action != "new release":
                serial = max(serial, int(entry_serial))
                continue
            package = {"name": name, "repo": None}
            events = self.pypi.events(package, "reference" if name in self.reference else "ground_truth", self.reference, stamp)
            # В глобальном потоке не предполагаем monitored: принадлежность периметру назначается отдельно.
            for event in events:
                if event["event"]["action"] == "package.release" and event["package"].get("version") != version:
                    continue
                if self.spool.enqueue(event):
                    accepted += 1
            serial = max(serial, int(entry_serial))
        save(self.state_path, make_state([], datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        state = load(self.state_path)
        state.next_cursor = str(serial)
        save(self.state_path, state)
        return {"changelog_entries": len(entries), "accepted": accepted, "next_serial": serial}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-pypi-global")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--state", type=Path, default=Path(".sscs/global-pypi-state.json"))
    parser.add_argument("--spool", type=Path, default=Path(".sscs/spool"))
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args(argv)
    reference = json.loads(args.reference.read_text()) if args.reference else []
    collector = GlobalPyPICollector(DiskSpool(args.spool), args.state, reference)
    try:
        result = {"available": collector.check()} if args.check else collector.run_once()
    except ChangelogUnavailable as exc:
        print(json.dumps({"available": False, "fallback": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
