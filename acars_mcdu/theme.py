"""Paleta y QSS: estética glass-cockpit moderna (A350/EFB)."""

from PyQt6.QtGui import QColor, QFont, QFontDatabase

BG = "#070b10"
SURFACE = "#0e141c"
SURFACE_2 = "#131b25"
BORDER = "#1f2b38"
BORDER_HI = "#2d3f52"
TEXT = "#dde6f0"
MUTED = "#7a8da1"
CYAN = "#22d3ee"
GREEN = "#34e39b"
AMBER = "#ffb02e"
MAGENTA = "#e879f9"
RED = "#ff5470"
WHITE = "#f2f6fb"
BLUE = "#60a5fa"

C = {k: QColor(v) for k, v in dict(
    bg=BG, surface=SURFACE, surface2=SURFACE_2, border=BORDER, border_hi=BORDER_HI,
    text=TEXT, muted=MUTED, cyan=CYAN, green=GREEN, amber=AMBER, magenta=MAGENTA,
    red=RED, white=WHITE, blue=BLUE,
).items()}


def mono(size=12, weight=QFont.Weight.Medium):
    for name in ("JetBrains Mono", "Fira Code", "DejaVu Sans Mono",
                 "Liberation Mono", "Noto Sans Mono", "monospace"):
        if name in QFontDatabase.families() or name == "monospace":
            f = QFont(name, size)
            break
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setWeight(weight)
    return f


def sans(size=10, weight=QFont.Weight.Medium):
    for name in ("Inter", "Inter Display", "Ubuntu", "Noto Sans", "DejaVu Sans",
                 "sans-serif"):
        if name in QFontDatabase.families() or name == "sans-serif":
            f = QFont(name, size)
            break
    f.setWeight(weight)
    return f


QSS = f"""
* {{ outline: 0; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 12px; }}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#cardFlat {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#cardTitle {{
    color: {MUTED}; font-size: 10px; font-weight: 700;
    letter-spacing: 2px; padding: 0 2px;
}}
QLabel#value {{ color: {WHITE}; font-size: 15px; font-weight: 600; }}
QLabel#valueBig {{ color: {CYAN}; font-size: 22px; font-weight: 700; }}
QLabel#key {{ color: {MUTED}; font-size: 10px; letter-spacing: 1px; }}

QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    color: {TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton:hover {{ background: #1a2431; border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background: #22303f; }}
QPushButton:checked {{
    background: rgba(34,211,238,0.14);
    border-color: {CYAN};
    color: {CYAN};
}}
QPushButton#lsk {{
    min-width: 34px; max-width: 46px; min-height: 26px;
    font-family: monospace; color: {MUTED};
}}
QPushButton#lsk:hover {{ color: {CYAN}; border-color: {CYAN}; }}
QPushButton#kp {{ min-width: 30px; min-height: 28px; font-size: 11px; }}
QPushButton#page {{ color: {MUTED}; }}
QPushButton#accent {{
    background: rgba(34,211,238,0.12); border-color: {CYAN}; color: {CYAN};
}}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER_HI}; border-radius: 6px; padding: 4px;
}}
QSplitter::handle {{ background: transparent; width: 8px; }}
"""
