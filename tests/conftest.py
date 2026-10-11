from pathlib import Path
import os
import sys

# Only the independent distribution is added, never the legacy repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from openbexi_ide.fonts import configure_fonts


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    configure_fonts(application)
    return application
