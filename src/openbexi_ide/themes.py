"""Restrained light and dark palettes shared by all native widgets."""
from PySide6.QtGui import QColor, QPalette

THEMES = {
    "light": dict(bg="#f5f5f7", surface="#ffffff", text="#24262b", muted="#747781",
                  border="#e3e4e8", accent="#3976dd", selected="#eaf1ff", gutter="#fafafb",
                  comment="#818892", keyword="#9c42ad", string="#347347", number="#b06e24"),
    "dark": dict(bg="#191b20", surface="#22252c", text="#e7e9ef", muted="#9da4b3",
                 border="#343943", accent="#82adff", selected="#303e59", gutter="#202329",
                 comment="#8f99ac", keyword="#cc9ae8", string="#a2d2ab", number="#e1b67d"),
}


def apply_theme(app, name: str) -> dict:
    colors = THEMES[name]
    palette = QPalette()
    for role, key in [(QPalette.Window, "bg"), (QPalette.Base, "surface"),
                      (QPalette.AlternateBase, "gutter"), (QPalette.WindowText, "text"),
                      (QPalette.Text, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.Highlight, "selected"),
                      (QPalette.HighlightedText, "text")]:
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["muted"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet("""
      QMainWindow, QDialog { background: %(bg)s; color: %(text)s; }
      QWidget { color: %(text)s; font-size: 13px; }
      QMenuBar { background: %(bg)s; padding: 3px 12px; }
      QMenu { background: %(surface)s; border: 1px solid %(border)s; padding: 6px; }
      QMenu::item { padding: 7px 24px; border-radius: 4px; }
      QMenu::item:selected { background: %(selected)s; }
      QToolBar { background: %(bg)s; border: none; padding: 8px 12px; spacing: 8px; }
      QToolButton, QPushButton { border: 1px solid transparent; border-radius: 7px;
        padding: 7px 12px; background: transparent; }
      QToolButton:hover, QPushButton:hover { background: %(selected)s; }
      QToolButton:disabled, QPushButton:disabled { color: %(muted)s; }
      QToolButton:focus, QPushButton:focus, QLineEdit:focus { border: 1px solid %(accent)s; }
      QTreeView { background: %(bg)s; border: none; padding: 4px; outline: none; }
      QTreeView::item { height: 28px; border-radius: 5px; }
      QTreeView::item:selected { background: %(selected)s; }
      QTabWidget::pane { border: 1px solid %(border)s; background: %(surface)s; }
      QTabBar::tab { background: %(bg)s; color: %(muted)s; padding: 10px 18px;
        border: none; border-bottom: 2px solid transparent; }
      QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(accent)s; }
      QPlainTextEdit { background: %(surface)s; border: none; selection-background-color: %(selected)s; }
      QPlainTextEdit { font-size: 14px; }
      QLineEdit, QComboBox { background: %(surface)s; border: 1px solid %(border)s;
        border-radius: 6px; padding: 7px 10px; }
      QSplitter::handle { background: %(border)s; }
      QStatusBar { background: %(bg)s; border: none; color: %(muted)s; padding: 3px 12px; }
      QLabel#muted, QLabel#sectionLabel { color: %(muted)s; }
      QLabel#sectionLabel { font-size: 11px; font-weight: 600; padding: 12px 16px; }
      QLabel#welcomeTitle { font-size: 27px; font-weight: 600; }
      QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
      QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 28px; }
      QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """ % colors)
    return colors
