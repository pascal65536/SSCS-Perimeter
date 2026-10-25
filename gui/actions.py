from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit

from .settings_client import SettingsClient


class AddPackageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить пакет в мониторинг")
        layout = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("например, requests")
        self.version = QLineEdit()
        self.version.setPlaceholderText("необязательно; иначе — последняя из PyPI")
        layout.addRow("Имя пакета", self.name)
        layout.addRow("Версия", self.version)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self) -> None:
        if self.name.text().strip():
            super().accept()

    def values(self) -> tuple[str, str | None]:
        return self.name.text().strip(), self.version.text().strip() or None


class RecalculateWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, settings_path: str, parent=None):
        super().__init__(parent)
        self.settings_path = settings_path

    def run(self) -> None:
        try:
            result = SettingsClient(self.settings_path).recalculate()
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
