"""Use native system fonts, including in a Windows offscreen QA session."""
import os
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


def configure_fonts(app):
    if not QFontDatabase.families() and os.name == "nt":
        # Qt's offscreen plugin cannot enumerate Windows fonts. Load installed
        # system files for rendering QA; no font is copied into the distribution.
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf", "consolab.ttf"):
            path = folder / filename
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        app.setFont(QFont("Segoe UI", 10))
    else:
        app.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))


def fixed_font():
    if "Consolas" in QFontDatabase.families():
        return QFont("Consolas", 10)
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)
