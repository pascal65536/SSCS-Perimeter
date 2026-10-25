from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .datalayer import DataBackend, risk_of

ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_PACKAGE = Qt.ItemDataRole.UserRole + 1

RISK_COLORS = {
    "critical": QColor("#dc2626"),
    "high": QColor("#ea580c"),
    "medium": QColor("#d97706"),
    "low": QColor("#15803d"),
    "none": QColor("#64748b"),
}


class PerimeterTree(QTreeWidget):
    package_selected = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, backend: DataBackend):
        super().__init__()
        self.backend = backend
        self.setHeaderLabels(["Периметр проекта", "Уровень", "Риск"])
        self.setColumnWidth(0, 330)
        self.setColumnWidth(1, 90)
        self.itemSelectionChanged.connect(self._selected)
        self.itemExpanded.connect(self._expanded)
        self.reload()

    def reload(self) -> None:
        self.clear()
        for project in self.backend.projects():
            project_item = QTreeWidgetItem([project, "PROJECT", ""])
            project_item.setData(0, ROLE_KIND, "project")
            project_item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
            self.addTopLevelItem(project_item)
            packages = self.backend.packages(project)
            roots = [p for p in packages if p.get("level") == "SELF"]
            if not roots:
                child_names = {dep for p in packages for dep in p.get("dependencies", [])}
                roots = [p for p in packages if p["name"] not in child_names]
            for package in roots:
                project_item.addChild(self._package_item(package))
            project_item.setExpanded(True)

    def _package_item(self, package: dict) -> QTreeWidgetItem:
        risk = risk_of(package)
        severity = str(risk.get("severity", "none")).lower()
        label = "нет данных" if severity == "none" else severity.upper()
        item = QTreeWidgetItem([package["name"], package.get("level", "INDIRECT"), label])
        item.setData(0, ROLE_KIND, "package")
        item.setData(0, ROLE_PACKAGE, package["name"])
        item.setToolTip(0, f"{package['name']} {package.get('version') or ''}".strip())
        color = RISK_COLORS.get(severity, RISK_COLORS["none"])
        for column in range(3):
            item.setForeground(column, color)
        if package.get("dependencies"):
            item.addChild(QTreeWidgetItem(["Загрузка…", "", ""]))
        return item

    def _expanded(self, item: QTreeWidgetItem) -> None:
        if item.data(0, ROLE_KIND) != "package" or item.childCount() != 1:
            return
        if item.child(0).data(0, ROLE_KIND) is not None:
            return
        package = item.data(0, ROLE_PACKAGE)
        item.takeChildren()
        try:
            for child in self.backend.children(package):
                item.addChild(self._package_item(child))
        except Exception as exc:
            self.error.emit(str(exc))
            item.addChild(QTreeWidgetItem(["Ошибка загрузки", "", ""]))

    def _selected(self) -> None:
        items = self.selectedItems()
        if items and items[0].data(0, ROLE_KIND) == "package":
            self.package_selected.emit(items[0].data(0, ROLE_PACKAGE))

    def select_package(self, package: str) -> None:
        def walk(item: QTreeWidgetItem):
            if item.data(0, ROLE_PACKAGE) == package:
                self.setCurrentItem(item)
                return True
            return any(walk(item.child(i)) for i in range(item.childCount()))

        for i in range(self.topLevelItemCount()):
            if walk(self.topLevelItem(i)):
                return
