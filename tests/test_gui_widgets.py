import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from gui.datalayer import DemoBackend
from gui.details import DetailsPanel
from gui.notes import NotesStore
from gui.tree import PerimeterTree

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_demo_tree_lazy_children_and_details(app, tmp_path):
    backend = DemoBackend(ROOT / "gui" / "demo_snapshot.json")
    tree = PerimeterTree(backend)
    project = tree.topLevelItem(0)
    assert project.text(0) == "my-flask-app"
    root_items = [project.child(i) for i in range(project.childCount())]
    flask = next(item for item in root_items if item.text(0) == "flask")
    assert flask.childCount() == 1  # lazy placeholder
    tree._expanded(flask)
    assert flask.childCount() == 5
    details = DetailsPanel(backend, NotesStore(tmp_path / "notes.json"))
    details.show_package("certifi")
    assert "certifi" in details.title.text()
    assert details.findings.rowCount() == 3
    assert not details.tp_button.isEnabled()
    details.note.setPlainText("Проверить происхождение риска")
    details._save_note()
    assert NotesStore(tmp_path / "notes.json").get("certifi").startswith("Проверить")
