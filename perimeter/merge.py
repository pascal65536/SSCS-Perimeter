from __future__ import annotations

from typing import Iterable

from .builder import BuildResult

LEVEL_RANK = {"SELF": 0, "DIRECT": 1, "INDIRECT": 2}


def merge_results(results: Iterable[BuildResult]) -> BuildResult:
    """Union периметров проектов с массивом perimeter_root на общих узлах."""
    merged: dict[str, dict] = {}
    warnings: list[str] = []
    for result in results:
        warnings.extend(result.warnings)
        for package in result.packages:
            name = package["name"]
            if name not in merged:
                merged[name] = {**package, "dependencies": set(package.get("dependencies", [])), "perimeter_root": set(package.get("perimeter_root", []))}
                continue
            current = merged[name]
            if LEVEL_RANK[package["level"]] < LEVEL_RANK[current["level"]]:
                metadata = {k: v for k, v in package.items() if k not in {"dependencies", "perimeter_root"}}
                current.update(metadata)
            current["dependencies"].update(package.get("dependencies", []))
            current["perimeter_root"].update(package.get("perimeter_root", []))
    packages = []
    for name in sorted(merged):
        package = merged[name]
        package["dependencies"] = sorted(package["dependencies"])
        package["perimeter_root"] = sorted(package["perimeter_root"])
        packages.append(package)
    return BuildResult(packages, sorted(set(warnings)))
