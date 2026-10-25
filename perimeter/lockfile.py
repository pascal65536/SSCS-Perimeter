from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from settings_manager import canonical_name


REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^]]+\])?\s*==\s*([^\s;\\]+)")


def read_lockfile(path: str | Path) -> list[dict[str, str | None]]:
    """Читает pinned-версии из requirements, Poetry, uv, PDM и Pipfile.lock."""
    path = Path(path)
    suffix = path.suffix.lower()
    if path.name == "Pipfile.lock":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = list((data.get("default") or {}).items())
        return _from_mapping(rows)
    if suffix == ".toml" or path.name in {"poetry.lock", "uv.lock", "pdm.lock"}:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        packages = data.get("package") or []
        result = []
        for pkg in packages:
            if pkg.get("name") and pkg.get("version"):
                result.append({"name": canonical_name(pkg["name"]), "version": str(pkg["version"])})
        return _unique(result)
    result = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-", "--")):
            continue
        match = REQUIREMENT.match(line)
        if match:
            result.append({"name": canonical_name(match.group(1)), "version": match.group(2)})
        elif re.match(r"^[A-Za-z0-9._-]+\s*(?:\[.*])?$", line):
            result.append({"name": canonical_name(line.split("[")[0]), "version": None})
    if not result:
        raise ValueError(f"В lock-файле {path} не найдено pinned-зависимостей")
    return _unique(result)


def _from_mapping(rows) -> list[dict[str, str | None]]:
    result = []
    for name, spec in rows:
        version = spec.get("version") if isinstance(spec, dict) else None
        if isinstance(version, str):
            version = version.removeprefix("==")
        result.append({"name": canonical_name(name), "version": version})
    return _unique(result)


def _unique(rows: list[dict]) -> list[dict]:
    result = {canonical_name(row["name"]): {"name": canonical_name(row["name"]), "version": row.get("version")} for row in rows}
    return [result[key] for key in sorted(result)]
