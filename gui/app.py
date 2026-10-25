from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from settings_manager import SettingsManager

from .actions import AddPackageDialog, RecalculateWorker
from .datalayer import BackendError, DataBackend, DemoBackend, LiveBackend
from .details import DetailsPanel
from .notes import NotesStore
from .settings_client import SettingsClient
from .snapshot import snapshot_from_settings
from .tree import PerimeterTree


class MainWindow(QMainWindow):
    def __init__(
        self,
        backend: DataBackend,
        *,
        settings_path: Path,
        snapshot_path: Path,
        notes: NotesStore,
        degradation_message: str | None = None,
    ):
        super().__init__()
        self.backend = backend
        self.settings_path = settings_path
        self.snapshot_path = snapshot_path
        self.notes = notes
        self.worker: RecalculateWorker | None = None
        self.setWindowTitle("SSCS-Perimeter — динамический периметр зависимостей")
        self.resize(1180, 780)
        self._build_ui()
        if degradation_message:
            self.statusBar().showMessage(degradation_message, 15000)
            QMessageBox.warning(self, "Переход в demo-режим", degradation_message)

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        title = QLabel("SSCS-Perimeter")
        title.setObjectName("appTitle")
        toolbar.addWidget(title)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Режим:"))
        self.mode = QComboBox()
        self.mode.addItems(["demo", "live"])
        self.mode.setCurrentText(self.backend.mode)
        self.mode.currentTextChanged.connect(self.switch_mode)
        toolbar.addWidget(self.mode)
        self.add_button = QPushButton("＋ Пакет")
        self.add_button.clicked.connect(self.add_package)
        self.recalc_button = QPushButton("Пересчитать периметр")
        self.recalc_button.clicked.connect(self.recalculate)
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("Экспорт снапшота")
        self.export_button.clicked.connect(self.export_snapshot)
        for button in (self.add_button, self.recalc_button, self.refresh_button, self.export_button):
            toolbar.addWidget(button)
        outer.addLayout(toolbar)
        splitter = QSplitter()
        self.tree = PerimeterTree(self.backend)
        self.details = DetailsPanel(self.backend, self.notes)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.details)
        splitter.setSizes([410, 770])
        outer.addWidget(splitter, 1)
        legend = QLabel("● high/critical   ● medium   ● low   ● нет данных")
        legend.setObjectName("legend")
        outer.addWidget(legend)
        self.setCentralWidget(central)
        self.tree.package_selected.connect(self.details.show_package)
        self.tree.error.connect(self.show_error)
        self.details.error.connect(self.show_error)
        self.details.feedback_requested.connect(self.mark_finding)
        self.details.note_saved.connect(lambda pkg: self.statusBar().showMessage(f"Заметка для {pkg} сохранена", 4000))
        self.statusBar().showMessage("Готово")
        self.setStyleSheet(
            """
            QMainWindow { background: #f8fafc; }
            QLabel#appTitle { font-size: 20px; font-weight: 700; color: #0f172a; padding: 6px; }
            QLabel#packageTitle { font-size: 18px; font-weight: 650; color: #0f172a; padding-top: 8px; }
            QLabel#legend { color: #475569; padding: 4px; }
            QPushButton { padding: 7px 11px; border: 1px solid #cbd5e1; border-radius: 5px; background: white; }
            QPushButton:hover { background: #f1f5f9; }
            QPushButton:disabled { color: #94a3b8; background: #f1f5f9; }
            QTreeWidget, QTableWidget, QPlainTextEdit { background: white; border: 1px solid #e2e8f0; }
            QGroupBox { font-weight: 600; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            """
        )

    def switch_mode(self, mode: str) -> None:
        if mode == self.backend.mode:
            return
        try:
            backend = self._backend_for(mode)
        except Exception as exc:
            QMessageBox.warning(self, "Live недоступен", f"Выполнен возврат в demo: {exc}")
            self.mode.blockSignals(True)
            self.mode.setCurrentText("demo")
            self.mode.blockSignals(False)
            backend = DemoBackend(self.snapshot_path)
        self._set_backend(backend)

    def _backend_for(self, mode: str) -> DataBackend:
        if mode == "demo":
            return DemoBackend(self.snapshot_path)
        settings = SettingsManager(self.settings_path).load()
        backend = LiveBackend(settings)
        backend.healthcheck()
        return backend

    def _set_backend(self, backend: DataBackend) -> None:
        self.backend = backend
        self.tree.backend = backend
        self.details.backend = backend
        self.tree.reload()
        self.details.clear()
        self.statusBar().showMessage(f"Режим: {backend.mode}", 4000)

    def add_package(self) -> None:
        dialog = AddPackageDialog(self)
        if not dialog.exec():
            return
        name, version = dialog.values()
        try:
            self._ensure_settings_for_edit()
            SettingsClient(self.settings_path).add_package(name, version)
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.statusBar().showMessage(f"Пакет {name} записан в settings.json; пересчёт запущен…")
        self._start_recalculate(select=name)

    def recalculate(self) -> None:
        try:
            self._ensure_settings_for_edit()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self._start_recalculate()

    def _start_recalculate(self, select: str | None = None) -> None:
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage("Пересчёт уже выполняется", 4000)
            return
        self.recalc_button.setEnabled(False)
        self.add_button.setEnabled(False)
        self.worker = RecalculateWorker(str(self.settings_path), self)
        self.worker.succeeded.connect(lambda result: self._recalculated(result, select))
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.recalc_button.setEnabled(True))
        self.worker.finished.connect(lambda: self.add_button.setEnabled(True))
        self.worker.start()

    def _recalculated(self, result, select: str | None) -> None:
        try:
            settings = SettingsManager(self.settings_path).load()
            if self.backend.mode == "live":
                self._set_backend(LiveBackend(settings))
            else:
                old = self.backend
                data = snapshot_from_settings(settings)
                old_by_name = {p["name"]: p for p in old.data.get("packages", [])}
                for package in data["packages"]:
                    if package["name"] in old_by_name and "risk" in old_by_name[package["name"]]:
                        package["risk"] = old_by_name[package["name"]]["risk"]
                data["findings"] = old.data.get("findings", [])
                self._set_backend(DemoBackend(data))
            if select:
                self.tree.select_package(select)
            message = f"Периметр пересчитан: {len(result.packages)} пакетов"
            if result.warnings:
                message += f"; предупреждений: {len(result.warnings)}"
            self.statusBar().showMessage(message, 10000)
        except Exception as exc:
            self.show_error(str(exc))

    def _ensure_settings_for_edit(self) -> None:
        if self.settings_path.exists():
            return
        snapshot = DemoBackend(self.snapshot_path)
        settings = SettingsManager(self.settings_path).load_or_default(snapshot.data["project"]["name"])
        settings["project"] = snapshot.data["project"]
        settings["perimeter"]["packages"] = [
            {k: v for k, v in pkg.items() if k != "risk"} for pkg in snapshot.data["packages"]
        ]
        SettingsManager(self.settings_path).save(settings)

    def refresh(self) -> None:
        try:
            if self.backend.mode == "live":
                self.backend = self._backend_for("live")
                self._set_backend(self.backend)
            else:
                self.tree.reload()
                self.details.clear()
        except Exception as exc:
            self.show_error(str(exc))

    def export_snapshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт demo-снапшота", "sscs-snapshot.json", "JSON (*.json)")
        if not path:
            return
        try:
            self.backend.export_snapshot(path)
            self.statusBar().showMessage(f"Снапшот экспортирован: {path}", 8000)
        except Exception as exc:
            self.show_error(str(exc))

    def mark_finding(self, finding_id: str, label: str) -> None:
        try:
            self.backend.mark_finding(finding_id, label)
            self.statusBar().showMessage(f"Метка {label} записана в OpenSearch", 6000)
            if self.details.package:
                self.details.show_package(self.details.package)
        except Exception as exc:
            self.show_error(str(exc))

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 12000)
        QMessageBox.critical(self, "SSCS-Perimeter", message)


def create_backend(mode: str, settings_path: Path, snapshot_path: Path):
    if mode == "demo":
        return DemoBackend(snapshot_path), None
    try:
        backend = LiveBackend(SettingsManager(settings_path).load())
        backend.healthcheck()
        return backend, None
    except Exception as exc:
        message = f"OpenSearch недоступен ({exc}). Приложение продолжит работу из встроенного снапшота без сети."
        return DemoBackend(snapshot_path), message


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sscs-gui")
    parser.add_argument("--mode", choices=["auto", "live", "demo"], default="auto")
    parser.add_argument("--settings", type=Path, default=Path("settings.json"))
    parser.add_argument("--snapshot", type=Path, default=Path(__file__).with_name("demo_snapshot.json"))
    parser.add_argument("--notes", type=Path, default=None)
    args = parser.parse_args(argv)
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("SSCS-Perimeter")
    try:
        backend, warning = create_backend(args.mode, args.settings, args.snapshot)
    except Exception as exc:
        QMessageBox.critical(None, "Ошибка запуска", str(exc))
        return 2
    window = MainWindow(
        backend,
        settings_path=args.settings,
        snapshot_path=args.snapshot,
        notes=NotesStore(args.notes),
        degradation_message=warning,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
