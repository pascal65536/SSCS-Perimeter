from __future__ import annotations

import copy
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .snapshot import load_snapshot, save_snapshot

NO_RISK = {"severity": "none", "score": None, "rules": [], "updated_at": None}


class BackendError(RuntimeError):
    pass


class DataBackend(ABC):
    mode = "abstract"
    can_write_feedback = False

    @abstractmethod
    def projects(self) -> list[str]: ...

    @abstractmethod
    def packages(self, project: str) -> list[dict[str, Any]]: ...

    def children(self, package: str) -> list[dict[str, Any]]:
        node = self.node(package)
        by_name = {p["name"]: p for project in self.projects() for p in self.packages(project)}
        return [copy.deepcopy(by_name[name]) for name in node.get("dependencies", []) if name in by_name]

    def _project_of(self, package: str) -> str:
        node = self.node(package)
        roots = node.get("perimeter_root") or []
        if roots:
            return roots[0]
        projects = self.projects()
        if projects:
            return projects[0]
        raise BackendError(f"Пакет {package} не принадлежит проекту")

    @abstractmethod
    def node(self, package: str) -> dict[str, Any]: ...

    def details(self, package: str) -> dict[str, Any]:
        result = self.node(package)
        result["findings"] = self.findings(package)
        return result

    @abstractmethod
    def findings(self, package: str) -> list[dict[str, Any]]: ...

    def mark_finding(self, finding_id: str, label: str, comment: str = "") -> None:
        raise BackendError("Запись обратной связи доступна только в live-режиме")

    def export_snapshot(self, path: str | Path) -> None:
        projects = self.projects()
        packages = []
        for project in projects:
            packages.extend(self.packages(project))
        data = {
            "snapshot_version": "1.0",
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "project": {"name": projects[0] if projects else "exported-project", "roots": []},
            "packages": packages,
            "findings": [f for pkg in packages for f in self.findings(pkg["name"])],
        }
        save_snapshot(data, path)


class DemoBackend(DataBackend):
    mode = "demo"

    def __init__(self, snapshot: str | Path | dict[str, Any]):
        self.data = load_snapshot(snapshot) if isinstance(snapshot, (str, Path)) else copy.deepcopy(snapshot)
        if self.data.get("snapshot_version") != "1.0":
            raise BackendError("Неподдерживаемый demo-снапшот")
        self._packages = {p["name"]: p for p in self.data.get("packages", [])}
        self._findings = {}
        for finding in self.data.get("findings", []):
            self._findings.setdefault(finding.get("package"), []).append(finding)

    def projects(self) -> list[str]:
        roots = sorted({root for pkg in self._packages.values() for root in pkg.get("perimeter_root", [])})
        return roots or [self.data.get("project", {}).get("name", "demo-project")]

    def packages(self, project: str) -> list[dict[str, Any]]:
        result = []
        for package in sorted(self._packages):
            pkg = self._packages[package]
            if project in (pkg.get("perimeter_root") or [project]):
                result.append(copy.deepcopy(pkg))
        return result

    def node(self, package: str) -> dict[str, Any]:
        if package not in self._packages:
            raise BackendError(f"Пакет не найден в снапшоте: {package}")
        return copy.deepcopy(self._packages[package])

    def findings(self, package: str) -> list[dict[str, Any]]:
        return sorted(copy.deepcopy(self._findings.get(package, [])), key=lambda f: f.get("@timestamp", ""), reverse=True)

    def export_snapshot(self, path: str | Path) -> None:
        save_snapshot(self.data, path)


class LiveBackend(DataBackend):
    mode = "live"
    can_write_feedback = True

    def __init__(self, settings: dict[str, Any], *, client: Any | None = None):
        self.settings = copy.deepcopy(settings)
        self.siem = settings["siem"]
        self._packages = {p["name"]: p for p in settings["perimeter"]["packages"]}
        self.client = client or self._make_client()

    def _make_client(self):
        try:
            from opensearchpy import OpenSearch
        except ImportError as exc:
            raise BackendError("Для live-режима установите opensearch-py") from exc
        auth = None
        username = os.environ.get("SSCS_OPENSEARCH_USERNAME")
        password = os.environ.get("SSCS_OPENSEARCH_PASSWORD")
        if username and password:
            auth = (username, password)
        kwargs = {
            "hosts": [self.siem["url"]],
            "use_ssl": self.siem["url"].startswith("https"),
            "verify_certs": self.siem.get("verify_tls", True),
            "timeout": 15,
        }
        if auth:
            kwargs["http_auth"] = auth
        token = os.environ.get("SSCS_OPENSEARCH_TOKEN")
        if token:
            kwargs["headers"] = {"Authorization": f"Bearer {token}"}
        return OpenSearch(**kwargs)

    def healthcheck(self) -> None:
        try:
            self.client.info()
        except Exception as exc:
            raise BackendError(f"OpenSearch недоступен: {type(exc).__name__}") from exc

    def projects(self) -> list[str]:
        return sorted({root for pkg in self._packages.values() for root in pkg.get("perimeter_root", [])}) or [self.settings["project"]["name"]]

    def packages(self, project: str) -> list[dict[str, Any]]:
        return [self.node(name) for name in sorted(self._packages) if project in (self._packages[name].get("perimeter_root") or [project])]

    def node(self, package: str) -> dict[str, Any]:
        if package not in self._packages:
            raise BackendError(f"Пакет отсутствует в settings.json: {package}")
        result = copy.deepcopy(self._packages[package])
        result["risk"] = self._risk(package)
        return result

    def _risk(self, package: str) -> dict[str, Any]:
        body = {
            "size": 1,
            "query": {"term": {"package.name.keyword": package}},
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        try:
            hits = self.client.search(index=self.siem["scores_index"], body=body).get("hits", {}).get("hits", [])
            if not hits:
                return copy.deepcopy(NO_RISK)
            source = hits[0]["_source"]
            return source.get("risk") or source.get("sscs", {}).get("risk") or source
        except Exception as exc:
            raise BackendError(f"Не удалось получить риск {package}: {type(exc).__name__}") from exc

    def findings(self, package: str) -> list[dict[str, Any]]:
        body = {
            "size": 100,
            "query": {"term": {"package.name.keyword": package}},
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        try:
            hits = self.client.search(index=self.siem["findings_index"], body=body).get("hits", {}).get("hits", [])
            result = []
            for hit in hits:
                finding = hit["_source"]
                finding.setdefault("id", hit["_id"])
                finding.setdefault("package", package)
                result.append(finding)
            return result
        except Exception as exc:
            raise BackendError(f"Не удалось получить находки {package}: {type(exc).__name__}") from exc

    def mark_finding(self, finding_id: str, label: str, comment: str = "") -> None:
        if label not in {"true_positive", "false_positive"}:
            raise ValueError("Недопустимая метка")
        document = {
            "finding_id": finding_id,
            "label": label,
            "comment": comment,
            "labeled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "sscs-gui",
        }
        try:
            self.client.index(index=self.siem["feedback_index"], id=finding_id, body=document, refresh="wait_for")
        except Exception as exc:
            raise BackendError(f"Не удалось записать метку: {type(exc).__name__}") from exc


def risk_of(package: dict[str, Any]) -> dict[str, Any]:
    risk = package.get("risk")
    return risk if isinstance(risk, dict) else copy.deepcopy(NO_RISK)
