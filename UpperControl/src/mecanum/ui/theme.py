"""Qt theme: palette, fonts and shared stylesheet."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = QColor("#12151a")
PANEL = QColor("#1b1f27")
PANEL_ALT = QColor("#232833")
BORDER = QColor("#2e3542")
TEXT = QColor("#e6e9ef")
TEXT_DIM = QColor("#8b93a3")
ACCENT = QColor("#4aa3ff")
OK = QColor("#3ecf8e")
WARN = QColor("#ffb020")
DANGER = QColor("#ff4d4f")

STYLESHEET = f"""
QWidget {{
    background-color: {BG.name()};
    color: {TEXT.name()};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}
QGroupBox {{
    background-color: {PANEL.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_DIM.name()};
}}
QLabel[role="dim"] {{ color: {TEXT_DIM.name()}; }}
QLabel[role="value"] {{
    color: {TEXT.name()};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 13px;
}}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 700; }}
QPushButton {{
    background-color: {PANEL_ALT.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT.name()}; }}
QPushButton:pressed {{ background-color: {BORDER.name()}; }}
QPushButton:disabled {{ color: {TEXT_DIM.name()}; border-color: {BORDER.lighter(110).name()}; }}
QPushButton[role="danger"] {{
    background-color: {DANGER.name()};
    border-color: {DANGER.lighter(120).name()};
    color: #ffffff;
    font-weight: 700;
    font-size: 15px;
}}
QPushButton[role="danger"]:pressed {{ background-color: {DANGER.darker(120).name()}; }}
QPushButton[role="ok"] {{ border-color: {OK.name()}; }}
QComboBox {{
    background-color: {PANEL_ALT.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 6px;
    padding: 6px 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_ALT.name()};
    border: 1px solid {BORDER.name()};
    selection-background-color: {ACCENT.name()};
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: {BORDER.name()};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 15px;
    margin: -6px 0;
    border-radius: 8px;
    background: {ACCENT.name()};
}}
QSlider::sub-page:horizontal {{ background: {ACCENT.darker(130).name()}; border-radius: 2px; }}
QCheckBox {{ spacing: 8px; }}
QStatusBar {{ background-color: {PANEL.name()}; color: {TEXT_DIM.name()}; }}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the dark palette and stylesheet."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, BG)
    palette.setColor(QPalette.ColorRole.WindowText, TEXT)
    palette.setColor(QPalette.ColorRole.Base, PANEL)
    palette.setColor(QPalette.ColorRole.AlternateBase, PANEL_ALT)
    palette.setColor(QPalette.ColorRole.Text, TEXT)
    palette.setColor(QPalette.ColorRole.Button, PANEL_ALT)
    palette.setColor(QPalette.ColorRole.ButtonText, TEXT)
    palette.setColor(QPalette.ColorRole.Highlight, ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0b0e13"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, PANEL_ALT)
    palette.setColor(QPalette.ColorRole.ToolTipText, TEXT)
    app.setPalette(palette)

    app.setStyleSheet(STYLESHEET)

    app.setFont(ui_font(9))


def hex_of(colour: QColor | str) -> str:
    """Return a ``#rrggbb`` string for use inside a Qt stylesheet.

    Qt stylesheets need a colour literal; interpolating a QColor object
    yields something like ``PySide6.QtGui.QColor(...)`` which Qt silently
    refuses to parse.
    """
    if isinstance(colour, QColor):
        return colour.name()
    return colour


def ui_font(size: int = 9) -> QFont:
    """Font for Chinese UI text.

    "Segoe UI" has no CJK glyphs, so using it for Chinese renders every
    character as a box. Microsoft YaHei UI ships with Windows and covers
    both.
    """
    font = QFont("Microsoft YaHei UI", size)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    return font


def mono_font(size: int = 9) -> QFont:
    """Monospaced font for numeric readouts.

    Cascadia Mono is Latin-only, which is exactly what is wanted here:
    every string drawn with it is a number, a wheel name or a protocol
    token, so digits stay column-aligned. Chinese text must not use it.
    """
    font = QFont("Cascadia Mono", size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font
