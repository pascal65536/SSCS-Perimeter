from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from settings_manager import SettingsManager, canonical_name

from .clients import DepsDevClient, PyPIClient, package_metadata
from .http import HttpError
from .lockfile import read_lockfile


@dataclass
class BuildResult:
    packages: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self, generated_at: str | None = None) -> dict[str, Any]:
        return {"generated_at": generated_at, "packages": self.packages, "warnings": self.warnings}


@dataclass
class _Node:
    name: str
    version: str
    depth: int
    dependencies: set[str] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)


class PerimeterBuilder:
    """Объединяет resolved-графы deps.dev и обогащает узлы метаданными PyPI."""

    def __init__(
        self,
        depsdev: DepsDevClient | None = None,
        pypi: PyPIClient | None = None,
        *,
        max_workers: int = 8,
    ):
        self.depsdev = depsdev or DepsDevClient()
        self.pypi = pypi or PyPIClient()
        self.max_workers = max_workers

    def build(
        self,
        roots: Iterable[dict[str, str | None]],
        *,
        project_name: str = "my-project",
    ) -> BuildResult:
        root_list = sorted(
            ({"name": canonical_name(r["name"]), "version": r.get("version")} for r in roots),
            key=lambda r: r["name"],
        )
        if not root_list:
            return BuildResult([], ["Не заданы корневые пакеты"])
        warnings: list[str] = []
        self._resolve_versions(root_list, warnings)
        resolved = [r for r in root_list if r.get("version")]
        nodes: dict[str, _Node] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self.depsdev.dependencies, r["name"], r["version"]): r
                for r in resolved
            }
            for future in as_completed(futures):
                root = futures[future]
                try:
                    graph = future.result()
                    self._merge_graph(nodes, graph, root, project_name, warnings)
                except HttpError as exc:
                    warnings.append(f"{root['name']}: граф deps.dev недоступен ({exc}); узел пропущен")
                except (KeyError, TypeError, ValueError) as exc:
                    warnings.append(f"{root['name']}: некорректный ответ deps.dev: {exc}; узел пропущен")
        self._remove_dangling_edges(nodes)
        self._enrich(nodes, warnings)
        packages = []
        for name in sorted(nodes):
            node = nodes[name]
            level = "SELF" if node.depth == 0 else "DIRECT" if node.depth == 1 else "INDIRECT"
            packages.append(
                {
                    "name": node.name,
                    "version": node.version,
                    "level": level,
                    "dependencies": sorted(node.dependencies),
                    "perimeter_root": sorted(node.roots),
                    **getattr(node, "metadata", {
                        "summary": "Метаданные PyPI недоступны.",
                        "repo": None,
                        "pypi_url": f"https://pypi.org/project/{node.name}/",
                        "releases": [],
                    }),
                }
            )
        return BuildResult(packages, sorted(set(warnings)))

    def build_projects(self, projects: Iterable[dict[str, Any]]) -> BuildResult:
        """Строит и объединяет периметры нескольких независимых проектов."""
        from .merge import merge_results
        results = [self.build(project["roots"], project_name=project["name"]) for project in projects]
        return merge_results(results)

    def rebuild(self, settings_path: str, *, generated_at: str | None = None) -> BuildResult:
        manager = SettingsManager(settings_path)
        settings = manager.load()
        result = self.build(settings["project"]["roots"], project_name=settings["project"]["name"])
        stamp = generated_at if generated_at is not None else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        manager.replace_perimeter(result.packages, stamp)
        return result

    def build_lockfile(self, path: str, *, project_name: str = "my-project") -> BuildResult:
        return self.build(read_lockfile(path), project_name=project_name)

    def _resolve_versions(self, roots: list[dict], warnings: list[str]) -> None:
        missing = [r for r in roots if not r.get("version")]
        if not missing:
            return
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self.pypi.package, r["name"]): r for r in missing}
            for future in as_completed(futures):
                root = futures[future]
                try:
                    data = future.result()
                    version = (data.get("info") or {}).get("version")
                    if not version:
                        raise ValueError("info.version отсутствует")
                    root["version"] = str(version)
                    root["_pypi"] = data
                except (HttpError, ValueError) as exc:
                    warnings.append(f"{root['name']}: не удалось определить версию через PyPI: {exc}")

    def _merge_graph(
        self,
        target: dict[str, _Node],
        graph: dict[str, Any],
        root: dict,
        project_name: str,
        warnings: list[str],
    ) -> None:
        raw_nodes = graph.get("nodes")
        raw_edges = graph.get("edges") or []
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise ValueError("nodes пуст или отсутствует")
        parsed: list[tuple[str, str]] = []
        for raw in raw_nodes:
            key = raw.get("versionKey") or raw.get("version_key")
            if not key or str(key.get("system", "PYPI")).upper() != "PYPI":
                raise ValueError("узел без versionKey системы PYPI")
            parsed.append((canonical_name(key["name"]), str(key["version"])))
        adjacency: dict[int, set[int]] = {i: set() for i in range(len(parsed))}
        reverse: dict[int, set[int]] = {i: set() for i in range(len(parsed))}
        for edge in raw_edges:
            source = int(edge.get("fromNode", edge.get("from_node")))
            dest = int(edge.get("toNode", edge.get("to_node")))
            if source in adjacency and dest in adjacency:
                adjacency[source].add(dest)
                reverse[dest].add(source)
        root_indices = [i for i, (name, version) in enumerate(parsed) if name == root["name"] and version == root["version"]]
        start = root_indices[0] if root_indices else 0
        depths = {start: 0}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for dest in sorted(adjacency[current]):
                if dest not in depths:
                    depths[dest] = depths[current] + 1
                    queue.append(dest)
        for index, depth in depths.items():
            name, version = parsed[index]
            node = target.get(name)
            if node is None:
                node = _Node(name, version, depth)
                target[name] = node
            else:
                if depth < node.depth:
                    node.depth = depth
                    node.version = version
                elif node.version != version:
                    warnings.append(
                        f"Конфликт версий {name}: выбрана {node.version}, проигнорирована {version}"
                    )
            node.roots.add(project_name)
        for index in depths:
            source_name = parsed[index][0]
            for dest in adjacency[index]:
                if dest in depths:
                    target[source_name].dependencies.add(parsed[dest][0])

    def _enrich(self, nodes: dict[str, _Node], warnings: list[str]) -> None:
        def fetch(node: _Node):
            data = self.pypi.package(node.name)
            return node.name, package_metadata(data)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(fetch, node) for node in nodes.values()]
            for future in as_completed(futures):
                try:
                    name, metadata = future.result()
                    nodes[name].metadata = metadata
                except HttpError as exc:
                    # Имя недоступно из-за конкурентного future; текст не содержит секретов.
                    warnings.append(f"Метаданные PyPI не получены: {exc}; repo=null")

    @staticmethod
    def _remove_dangling_edges(nodes: dict[str, _Node]) -> None:
        for node in nodes.values():
            node.dependencies.intersection_update(nodes)
