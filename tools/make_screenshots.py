#!/usr/bin/env python3
"""Genera las capturas de docs/ con datos en vivo (ADS-B real, sin radio).

   QT_QPA_PLATFORM=offscreen python3 make_screenshots.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import types

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from acars_mcdu import config
from acars_mcdu import main as M
from acars_mcdu import theme as T
from acars_mcdu.sourcedialog import SourceDialog

OUT = "docs"
W, H = 1700, 980


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = config.load()
    cfg["source"]["mode"] = "udp"          # nada de radio al sacar capturas
    app = QApplication(sys.argv)
    app.setStyleSheet(T.QSS)
    win = M.Window(cfg, types.SimpleNamespace(spawn=False))
    win.resize(W, H)
    win.show()

    def shot(name, widget=None):
        app.processEvents()
        (widget or win).repaint()
        app.processEvents()
        (widget or win).grab().save(os.path.join(OUT, name + ".png"))
        print("  ", name)

    def pick_target():
        """Elige el avión con más parámetros disponibles."""
        best, score = None, -1
        for h, a in win.map.traffic.items():
            s = sum(1 for k in ("ias", "tas", "mach", "wd", "oat", "roll",
                                "nav_altitude_mcp", "nav_heading", "squawk")
                    if a.get(k) is not None)
            if s > score:
                best, score = h, s
        if best:
            win.select_hex(best)
            win.map.zoom = 7
            print("objetivo:", best, win.map.traffic[best].get("flight"))

    def pages():
        real = [m for m in win.mcdu.msgs if '"SIM"' not in (m.get("raw") or "")]
        if real:
            win.mcdu.msgs = real          # las capturas muestran tráfico real
        for page, name in (("INDEX", "01-index"), ("MSGLOG", "02-msglog"),
                           ("FLTDATA", "04-fltdata"), ("ACDATA", "05-acdata"),
                           ("RADIO", "06-radio"), ("STATUS", "07-status"),
                           ("ATC", "08-atc")):
            win.mcdu.goto(page)
            shot(name)
            if page == "MSGLOG" and win.mcdu.msgs:
                win.mcdu._open_msg(win.mcdu.msgs[0])
                shot("03-msgdet")
        win.mcdu.goto("INDEX")
        shot("layout")

    def dialog():
        d = SourceDialog(cfg, win.src.mode, win)
        d.show()
        for i, name in enumerate(("09-source-rtl", "10-source-udp",
                                  "11-source-cmd", "12-source-sim")):
            d.mode.setCurrentIndex(i)
            shot(name, d)
        d.close()

    QTimer.singleShot(6000, pick_target)
    QTimer.singleShot(11000, pages)
    QTimer.singleShot(14000, dialog)
    QTimer.singleShot(16000, app.quit)
    app.exec()
    print("capturas en", OUT + "/")


if __name__ == "__main__":
    main()
