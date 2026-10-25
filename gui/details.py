from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .datalayer import DataBackend, risk_of
from .notes import NotesStore


class DetailsPanel(QWidget):
    feedback_requested = pyqtSignal(str, str)
    note_saved = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, backend: DataBackend, notes: NotesStore):
        super().__init__()
        self.backend = backend
        self.notes = notes
        self.package: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.title = QLabel("Выберите пакет в дереве")
        self.title.setObjectName("packageTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.risk = QLabel("")
        layout.addWidget(self.risk)
        self.description = QLabel("")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        links_layout = QHBoxLayout()
        self.pypi_link = QLabel("PyPI: —")
        self.repo_link = QLabel("GitHub: —")
        for label in (self.pypi_link, self.repo_link):
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            links_layout.addWidget(label)
        links_layout.addStretch(1)
        layout.addLayout(links_layout)

        versions_group = QGroupBox("Последние версии")
        versions_layout = QVBoxLayout(versions_group)
        self.versions = QTableWidget(0, 2)
        self.versions.setHorizontalHeaderLabels(["Версия", "Дата UTC"])
        self.versions.horizontalHeader().setStretchLastSection(True)
        self.versions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.versions.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.versions.setMaximumHeight(150)
        versions_layout.addWidget(self.versions)
        layout.addWidget(versions_group)

        findings_group = QGroupBox("Находки и алерты")
        findings_layout = QVBoxLayout(findings_group)
        self.findings = QTableWidget(0, 4)
        self.findings.setHorizontalHeaderLabels(["Дата", "Правило", "Уровень", "Статус"])
        self.findings.horizontalHeader().setStretchLastSection(True)
        self.findings.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.findings.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.findings.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.findings.itemSelectionChanged.connect(self._update_feedback_buttons)
        findings_layout.addWidget(self.findings)
        feedback_layout = QHBoxLayout()
        self.tp_button = QPushButton("Истинная (TP)")
        self.fp_button = QPushButton("Ложная (FP)")
        self.tp_button.clicked.connect(lambda: self._feedback("true_positive"))
        self.fp_button.clicked.connect(lambda: self._feedback("false_positive"))
        feedback_layout.addWidget(self.tp_button)
        feedback_layout.addWidget(self.fp_button)
        feedback_layout.addStretch(1)
        findings_layout.addLayout(feedback_layout)
        layout.addWidget(findings_group, 1)

        note_group = QGroupBox("Локальная заметка")
        note_layout = QVBoxLayout(note_group)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Заметка хранится только на этом компьютере")
        self.note.setMaximumHeight(90)
        self.save_note_button = QPushButton("Сохранить заметку")
        self.save_note_button.clicked.connect(self._save_note)
        note_layout.addWidget(self.note)
        note_layout.addWidget(self.save_note_button)
        layout.addWidget(note_group)
        self.clear()

    def clear(self) -> None:
        self.package = None
        self.title.setText("Выберите пакет в дереве")
        self.risk.clear()
        self.description.clear()
        self.versions.setRowCount(0)
        self.findings.setRowCount(0)
        self.note.clear()
        self._update_feedback_buttons()

    def show_package(self, package: str) -> None:
        try:
            data = self.backend.details(package)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.package = package
        self.title.setText(f"{package}  ·  {data.get('version') or 'версия не указана'}  ·  {data.get('level', '')}")
        risk = risk_of(data)
        severity = risk.get("severity", "none")
        score = risk.get("score")
        score_text = "—" if score is None else f"{float(score):.3f}"
        self.risk.setText(f"Риск: {str(severity).upper()}  ·  Score: {score_text}")
        self.description.setText(data.get("summary") or "Описание отсутствует")
        pypi = data.get("pypi_url") or f"https://pypi.org/project/{package}/"
        self.pypi_link.setText(f'<a href="{pypi}">Открыть PyPI</a>')
        repo = data.get("repo")
        self.repo_link.setText(f'<a href="https://github.com/{repo}">Открыть GitHub</a>' if repo else "GitHub: не сопоставлен")
        releases = data.get("releases") or []
        self.versions.setRowCount(len(releases))
        for row, release in enumerate(releases):
            self.versions.setItem(row, 0, QTableWidgetItem(str(release.get("version", ""))))
            self.versions.setItem(row, 1, QTableWidgetItem(str(release.get("released_at", ""))))
        findings = data.get("findings") or []
        self.findings.setRowCount(len(findings))
        for row, finding in enumerate(findings):
            values = [
                finding.get("@timestamp", ""),
                finding.get("rule_id") or finding.get("rule", ""),
                finding.get("severity", ""),
                finding.get("status", "new"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, finding.get("id") or finding.get("finding_id"))
                self.findings.setItem(row, column, item)
        self.note.setPlainText(self.notes.get(package))
        self._update_feedback_buttons()

    def _selected_finding(self) -> str | None:
        row = self.findings.currentRow()
        if row < 0 or not self.findings.item(row, 0):
            return None
        return self.findings.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _update_feedback_buttons(self) -> None:
        enabled = self.backend.can_write_feedback and self._selected_finding() is not None
        self.tp_button.setEnabled(enabled)
        self.fp_button.setEnabled(enabled)
        tooltip = "В demo-режиме запись в SIEM отключена" if not self.backend.can_write_feedback else "Выберите находку"
        self.tp_button.setToolTip(tooltip)
        self.fp_button.setToolTip(tooltip)

    def _feedback(self, label: str) -> None:
        finding_id = self._selected_finding()
        if finding_id:
            self.feedback_requested.emit(str(finding_id), label)

    def _save_note(self) -> None:
        if not self.package:
            return
        try:
            self.notes.set(self.package, self.note.toPlainText())
            self.note_saved.emit(self.package)
        except OSError as exc:
            self.error.emit(str(exc))
