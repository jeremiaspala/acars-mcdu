#!/usr/bin/env python3
"""Genera el icono de la app (docs/icon.png, 256x256)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import QApplication

from acars_mcdu import theme as T

S = 256


def main():
    app = QApplication(sys.argv)
    pm = QPixmap(S, S)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    body = QPainterPath()
    body.addRoundedRect(QRectF(6, 6, S - 12, S - 12), 56, 56)
    g = QLinearGradient(0, 0, 0, S)
    g.setColorAt(0, QColor("#16212c"))
    g.setColorAt(1, QColor("#070b10"))
    p.setBrush(QBrush(g))
    p.setPen(QPen(QColor("#2d3f52"), 3))
    p.drawPath(body)
    p.setClipPath(body)

    # rosa de rumbos
    c = QPointF(S / 2, S / 2 - 12)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(34, 211, 238, 60), 3))
    p.drawEllipse(c, 78, 78)
    p.setPen(QPen(QColor(34, 211, 238, 28), 2))
    p.drawEllipse(c, 98, 98)

    # avión
    p.save()
    p.translate(c)
    p.rotate(34)
    path = QPainterPath()
    pts = [(0, -52), (10, -14), (56, 15), (56, 25), (10, 14), (8, 40),
           (24, 54), (24, 61), (0, 53), (-24, 61), (-24, 54), (-8, 40),
           (-10, 14), (-56, 25), (-56, 15), (-10, -14)]
    k = 0.82
    path.moveTo(pts[0][0] * k, pts[0][1] * k)
    for x, y in pts[1:]:
        path.lineTo(x * k, y * k)
    path.closeSubpath()
    p.setPen(QPen(QColor(T.CYAN), 3))
    p.setBrush(QBrush(QColor(34, 211, 238, 90)))
    p.drawPath(path)
    p.restore()

    # texto ACARS
    f = T.mono(26, QFont.Weight.Bold)
    f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 6)
    p.setFont(f)
    p.setPen(QPen(QColor(T.GREEN)))
    p.drawText(QRectF(0, S - 62, S, 40), Qt.AlignmentFlag.AlignCenter, "ACARS")
    p.end()

    os.makedirs("docs", exist_ok=True)
    pm.save("docs/icon.png")
    for sz in (128, 64, 48, 32):
        pm.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio,
                  Qt.TransformationMode.SmoothTransformation).save(
            f"docs/icon-{sz}.png")
    print("docs/icon.png")


if __name__ == "__main__":
    main()
