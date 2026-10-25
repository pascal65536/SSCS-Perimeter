from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


class SettingsError(ValueError):
    """Конфигурация отсутствует, повреждена или не проходит валидацию."""


def canonical_name(name: str) -> str:
    """PEP 503: имя пакета приводится к единому виду для объединения графов."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def default_settings(project_name: str = "my-project") -> dict[str, Any]:
    return {
        "schema_version": "1.2",
        "project": {"name": project_name, "roots": []},
        "perimeter": {"generated_at": None, "packages": []},
        "reference": [],
        "polling": {
            "pypi_seconds": 300,
            "github_seconds": 300,
            "timeout_seconds": 20,
            "max_workers": 8,
        },
        "detectors": {
            "weights": {
                "SSCS-001": 0.7,
                "SSCS-002": 0.6,
                "SSCS-003": 0.8,
                "SSCS-004": 0.7,
                "SSCS-005": 0.5,
                "SSCS-006": 0.9,
                "SSCS-CHAIN": 0.95,
                "SSCS-DORM": 0.55,
            },
            "SSCS-001": {"max_distance": 2},
            "SSCS-002": {
                "burst_count": 7,
                "window_days": 7,
                "interval_ratio": 0.25,
            },
            "SSCS-005": {
                "night_hours": [0, 1, 2, 3, 4, 5, 6, 23],
                "warmup_commits": 10,
            },
            "SSCS-DORM": {"dormant_days": 180, "min_history": 2},
            "dedup_window_days": 7,
        },
        "spool": {"path": ".sscs/spool", "max_bytes": 67108864},
        "siem": {
            "url": "https://localhost:9200",
            "events_index": "sscs-events",
            "findings_index": "sscs-findings-*",
            "scores_index": "sscs-scores-*",
            "feedback_index": "sscs-feedback",
            "verify_tls": True,
        },
        "logging": {"level": "INFO"},
    }


class SettingsManager:
    """Единственная точка записи settings.json.

    Запись атомарна, сериализация детерминирована, секреты запрещены на
    уровне валидации. Методы не выполняют сетевых запросов.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise SettingsError(f"Файл конфигурации не найден: {self.path}")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SettingsError(f"Не удалось прочитать конфигурацию: {exc}") from exc
        self.validate(data)
        return data

    def load_or_default(self, project_name: str = "my-project") -> dict[str, Any]:
        return self.load() if self.path.exists() else default_settings(project_name)

    def save(self, data: dict[str, Any]) -> None:
        self.validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            data, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")
        ) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def initialize(self, project_name: str = "my-project", *, force: bool = False) -> dict:
        if self.path.exists() and not force:
            raise SettingsError(f"Конфигурация уже существует: {self.path}")
        data = default_settings(project_name)
        self.save(data)
        return data

    def add_root(self, name: str, version: str | None = None) -> dict[str, Any]:
        name = canonical_name(name)
        if not name:
            raise SettingsError("Имя пакета не может быть пустым")
        data = self.load()
        roots = data["project"]["roots"]
        if not any(canonical_name(r["name"]) == name for r in roots):
            roots.append({"name": name, "version": version or None})
            roots.sort(key=lambda r: canonical_name(r["name"]))
            self.save(data)
        return data

    def replace_perimeter(self, packages: list[dict], generated_at: str | None) -> dict:
        data = self.load()
        data["perimeter"] = {"generated_at": generated_at, "packages": packages}
        self.save(data)
        return data

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise SettingsError("Корень settings.json должен быть объектом")
        required = {
            "schema_version",
            "project",
            "perimeter",
            "reference",
            "polling",
            "detectors",
            "spool",
            "siem",
            "logging",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise SettingsError(f"Отсутствуют секции: {', '.join(missing)}")
        if data["schema_version"] != "1.2":
            raise SettingsError("Поддерживается только schema_version=1.2")
        project = data["project"]
        if not isinstance(project.get("name"), str) or not project["name"].strip():
            raise SettingsError("project.name должен быть непустой строкой")
        roots = project.get("roots")
        if not isinstance(roots, list):
            raise SettingsError("project.roots должен быть массивом")
        seen: set[str] = set()
        for root in roots:
            if not isinstance(root, dict) or not isinstance(root.get("name"), str):
                raise SettingsError("Каждый root должен содержать name")
            name = canonical_name(root["name"])
            if not name or name in seen:
                raise SettingsError(f"Пустое или повторное имя root: {name!r}")
            if root.get("version") is not None and not isinstance(root["version"], str):
                raise SettingsError(f"Версия root {name} должна быть строкой или null")
            seen.add(name)
        packages = data["perimeter"].get("packages")
        if not isinstance(packages, list):
            raise SettingsError("perimeter.packages должен быть массивом")
        package_names: set[str] = set()
        for pkg in packages:
            cls._validate_package(pkg)
            name = canonical_name(pkg["name"])
            if name in package_names:
                raise SettingsError(f"Повторный пакет периметра: {name}")
            package_names.add(name)
        for pkg in packages:
            for dep in pkg.get("dependencies", []):
                if canonical_name(dep) not in package_names:
                    raise SettingsError(
                        f"Неизвестная зависимость {dep!r} у пакета {pkg['name']!r}"
                    )
        if not isinstance(data["reference"], list) or not all(
            isinstance(x, str) for x in data["reference"]
        ):
            raise SettingsError("reference должен быть массивом строк")
        polling = data["polling"]
        for key in ("pypi_seconds", "github_seconds", "timeout_seconds", "max_workers"):
            if not isinstance(polling.get(key), int) or polling[key] <= 0:
                raise SettingsError(f"polling.{key} должен быть положительным целым")
        if not isinstance(data["spool"].get("max_bytes"), int) or data["spool"]["max_bytes"] < 1024:
            raise SettingsError("spool.max_bytes должен быть не меньше 1024")
        if data["logging"].get("level") not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise SettingsError("Недопустимый logging.level")
        cls._reject_secrets(data)

    @staticmethod
    def _validate_package(pkg: Any) -> None:
        if not isinstance(pkg, dict) or not isinstance(pkg.get("name"), str):
            raise SettingsError("Узел периметра должен содержать name")
        if not pkg["name"].strip():
            raise SettingsError("Имя узла периметра не может быть пустым")
        if pkg.get("level") not in {"SELF", "DIRECT", "INDIRECT"}:
            raise SettingsError(f"Недопустимый level у {pkg['name']}")
        if not isinstance(pkg.get("dependencies", []), list) or not all(
            isinstance(x, str) for x in pkg.get("dependencies", [])
        ):
            raise SettingsError(f"dependencies у {pkg['name']} должен быть массивом строк")
        roots = pkg.get("perimeter_root", [])
        if not isinstance(roots, list) or not all(isinstance(x, str) for x in roots):
            raise SettingsError(f"perimeter_root у {pkg['name']} должен быть массивом строк")
        if pkg.get("repo") is not None and not isinstance(pkg["repo"], str):
            raise SettingsError(f"repo у {pkg['name']} должен быть строкой или null")

    @classmethod
    def _reject_secrets(cls, value: Any, path: str = "settings") -> None:
        forbidden = {"password", "passwd", "token", "secret", "api_key", "apikey", "authorization"}
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower().replace("-", "_")
                if normalized in forbidden or normalized.endswith("_token"):
                    raise SettingsError(f"Секреты запрещены в конфигурации: {path}.{key}")
                cls._reject_secrets(child, f"{path}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                cls._reject_secrets(child, f"{path}[{i}]")

    def snapshot(self) -> dict[str, Any]:
        """Независимая копия для фоновых задач GUI."""
        return copy.deepcopy(self.load())
