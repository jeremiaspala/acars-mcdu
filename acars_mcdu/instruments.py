"""Instrumentos glass-cockpit dibujados con QPainter (PFD/HSI/VSI + grilla de datos)."""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                         QPolygonF, QLinearGradient)
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout, QWidget)

from . import theme as T


def _f(painter, size, weight=QFont.Weight.DemiBold):
    f = T.mono(size, weight)
    painter.setFont(f)
    return f


class _Base(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.state = {}

    def set_state(self, st):
        self.state = st or {}
        self.update()

    def _bg(self, p, r, radius=10):
        p.setPen(QPen(T.C["border"], 1))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#111a24"))
        g.setColorAt(1, QColor("#0a1016"))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


class Tape(_Base):
    """Cinta vertical tipo PFD. kind='spd' (IAS) o 'alt' (altitud barométrica)."""

    def __init__(self, kind="spd", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setMinimumSize(96, 220)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        self._bg(p, r)

        st = self.state
        if self.kind == "spd":
            val = st.get("ias")
            alt_val = st.get("tas")
            step, minor, label = 20, 10, "IAS"
            sub = f"M {st.get('mach'):.3f}" if st.get("mach") is not None else "M ---"
            sub2 = f"TAS {int(alt_val)}" if alt_val is not None else "TAS ---"
            bug = None
            fmt = lambda v: f"{int(round(v))}"
            px_per_unit = 2.2
        else:
            val = st.get("alt_baro")
            if val == "ground":
                val = 0
            step, minor, label = 500, 100, "ALT"
            qnh = st.get("nav_qnh")
            sub = f"QNH {qnh:.0f}" if qnh else "STD 1013"
            g = st.get("alt_geom")
            sub2 = f"GEO {int(g)}" if g is not None else "GEO ---"
            bug = st.get("nav_altitude_mcp") or st.get("nav_altitude_fms")
            fmt = lambda v: f"{int(round(v)):,}".replace(",", " ")
            px_per_unit = 0.11

        # marco interno
        pad = 8
        inner = QRectF(r.left() + pad, r.top() + 26, r.width() - 2 * pad,
                       r.height() - 26 - 46)
        cy = inner.center().y()

        p.setClipRect(inner)
        if val is None:
            p.setClipping(False)
            _f(p, 9)
            p.setPen(QPen(T.C["muted"]))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "NO DATA")
            self._header(p, r, label, sub, sub2)
            return

        # escala
        p.setPen(QPen(QColor("#2a3a4b"), 1))
        start = math.floor((val - inner.height() / 2 / px_per_unit) / minor) * minor
        end = val + inner.height() / 2 / px_per_unit + minor
        v = start
        _f(p, 9, QFont.Weight.Medium)
        while v <= end:
            y = cy - (v - val) * px_per_unit
            major = abs(v % step) < 1e-6
            if self.kind == "alt" and v < 0:
                v += minor
                continue
            if major:
                p.setPen(QPen(QColor("#3d556e"), 1.4))
                p.drawLine(QPointF(inner.right() - 16, y), QPointF(inner.right(), y))
                p.setPen(QPen(T.C["text"]))
                p.drawText(QRectF(inner.left(), y - 8, inner.width() - 20, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           fmt(v))
            else:
                p.setPen(QPen(QColor("#253545"), 1))
                p.drawLine(QPointF(inner.right() - 8, y), QPointF(inner.right(), y))
            v += minor

        # bug de altitud seleccionada
        if bug:
            y = cy - (bug - val) * px_per_unit
            p.setPen(QPen(T.C["magenta"], 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(inner.left() + 2, y - 5, inner.width() - 6, 10))

        p.setClipping(False)

        # ventana de valor actual
        wh = 26
        win = QRectF(inner.left() - 2, cy - wh / 2, inner.width() + 4, wh)
        path = QPainterPath()
        path.addRoundedRect(win, 5, 5)
        p.setBrush(QBrush(QColor(8, 12, 17, 235)))
        p.setPen(QPen(T.C["cyan"], 1.6))
        p.drawPath(path)
        _f(p, 14, QFont.Weight.Bold)
        p.setPen(QPen(T.C["white"]))
        p.drawText(win.adjusted(4, 0, -6, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   fmt(val))

        self._header(p, r, label, sub, sub2)

    def _header(self, p, r, label, sub, sub2):
        _f(p, 8, QFont.Weight.Bold)
        p.setPen(QPen(T.C["muted"]))
        p.drawText(QRectF(r.left(), r.top() + 6, r.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, label)
        _f(p, 8, QFont.Weight.Medium)
        p.setPen(QPen(T.C["cyan"]))
        p.drawText(QRectF(r.left(), r.bottom() - 28, r.width(), 12),
                   Qt.AlignmentFlag.AlignCenter, sub)
        p.setPen(QPen(T.C["muted"]))
        p.drawText(QRectF(r.left(), r.bottom() - 16, r.width(), 12),
                   Qt.AlignmentFlag.AlignCenter, sub2)


class VSI(_Base):
    """Variómetro vertical (baro_rate)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(62, 220)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        self._bg(p, r)
        rate = self.state.get("baro_rate")
        if rate is None:
            rate = self.state.get("geom_rate")

        inner = QRectF(r.left() + 6, r.top() + 24, r.width() - 12, r.height() - 46)
        cy = inner.center().y()
        half = inner.height() / 2

        def y_of(fpm):
            v = max(-6000, min(6000, fpm))
            # escala comprimida: 0-2000 lineal, 2000-6000 comprimido
            a = abs(v)
            frac = (a / 2000 * 0.62) if a <= 2000 else (0.62 + (a - 2000) / 4000 * 0.38)
            return cy - math.copysign(frac, v) * half

        _f(p, 8, QFont.Weight.Medium)
        for tick in (-6000, -4000, -2000, -1000, 0, 1000, 2000, 4000, 6000):
            y = y_of(tick)
            maj = tick % 2000 == 0
            p.setPen(QPen(QColor("#3d556e" if maj else "#253545"), 1.3 if maj else 1))
            p.drawLine(QPointF(inner.left(), y),
                       QPointF(inner.left() + (12 if maj else 7), y))
            if maj and tick:
                p.setPen(QPen(T.C["muted"]))
                p.drawText(QRectF(inner.left() + 13, y - 7, inner.width() - 14, 14),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           str(abs(tick) // 1000))

        p.setPen(QPen(QColor("#44607c"), 1.5))
        p.drawLine(QPointF(inner.left(), cy), QPointF(inner.right(), cy))

        if rate is not None:
            col = T.C["green"] if abs(rate) < 100 else (
                T.C["cyan"] if rate > 0 else T.C["amber"])
            y = y_of(rate)
            p.setPen(QPen(col, 2.4))
            p.drawLine(QPointF(inner.left() + 2, cy), QPointF(inner.right() - 2, y))
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(inner.right() - 4, y), 3, 3)
            _f(p, 9, QFont.Weight.Bold)
            p.setPen(QPen(col))
            p.drawText(QRectF(r.left(), r.bottom() - 18, r.width(), 14),
                       Qt.AlignmentFlag.AlignCenter, f"{int(rate):+d}")
        _f(p, 8, QFont.Weight.Bold)
        p.setPen(QPen(T.C["muted"]))
        p.drawText(QRectF(r.left(), r.top() + 6, r.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, "V/S")


class HSI(_Base):
    """Rosa de rumbos con track, heading magnético, bug de piloto automático,
    vector de viento e indicador de alabeo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        self._bg(p, r, 12)
        st = self.state
        cx, cy = r.center().x(), r.center().y() + 6
        rad = min(r.width(), r.height()) / 2 - 30

        trk = st.get("track")
        mhdg = st.get("mag_heading")
        thdg = st.get("true_heading")
        ref = trk if trk is not None else (thdg if thdg is not None else mhdg)

        _f(p, 8, QFont.Weight.Bold)
        p.setPen(QPen(T.C["muted"]))
        p.drawText(QRectF(r.left() + 10, r.top() + 6, 90, 14),
                   Qt.AlignmentFlag.AlignLeft, "HSI / TRK")

        if ref is None:
            _f(p, 9)
            p.setPen(QPen(T.C["muted"]))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "NO DATA")
            return

        # rosa
        p.save()
        p.translate(cx, cy)
        p.rotate(-ref)
        for deg in range(0, 360, 5):
            maj = deg % 30 == 0
            med = deg % 10 == 0
            ln = 11 if maj else (7 if med else 4)
            p.setPen(QPen(QColor("#3d556e" if maj else "#27394c"), 1.6 if maj else 1))
            p.save()
            p.rotate(deg)
            p.drawLine(QPointF(0, -rad), QPointF(0, -rad + ln))
            p.restore()
        p.restore()

        # etiquetas cardinales (horizontales)
        _f(p, 9, QFont.Weight.Bold)
        for deg, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W"),
                         (30, "3"), (60, "6"), (120, "12"), (150, "15"),
                         (210, "21"), (240, "24"), (300, "30"), (330, "33")):
            a = math.radians(deg - ref - 90)
            x = cx + math.cos(a) * (rad - 20)
            y = cy + math.sin(a) * (rad - 20)
            p.setPen(QPen(T.C["white"] if lab.isalpha() else T.C["muted"]))
            p.drawText(QRectF(x - 14, y - 8, 28, 16), Qt.AlignmentFlag.AlignCenter, lab)

        # índice superior (lubber line)
        p.setPen(QPen(T.C["white"], 2))
        p.drawLine(QPointF(cx, cy - rad - 6), QPointF(cx, cy - rad + 8))

        # bug de rumbo del piloto automático
        nav = st.get("nav_heading")
        if nav is not None:
            a = math.radians(nav - ref - 90)
            x, y = cx + math.cos(a) * rad, cy + math.sin(a) * rad
            p.save()
            p.translate(x, y)
            p.rotate(nav - ref)
            p.translate(-x, -y)
            p.setPen(QPen(T.C["magenta"], 1.5))
            p.setBrush(QBrush(T.C["magenta"]))
            p.drawPolygon(QPolygonF([QPointF(x, y + 1), QPointF(x - 7, y - 11),
                                     QPointF(x + 7, y - 11)]))
            p.restore()

        # silueta del avión alineada al track
        p.save()
        p.translate(cx, cy)
        path = QPainterPath()
        path.moveTo(0, -16)
        path.lineTo(3.2, -4)
        path.lineTo(17, 5)
        path.lineTo(17, 8)
        path.lineTo(3.2, 4.5)
        path.lineTo(2.6, 12)
        path.lineTo(7, 16)
        path.lineTo(7, 18)
        path.lineTo(0, 16)
        path.lineTo(-7, 18)
        path.lineTo(-7, 16)
        path.lineTo(-2.6, 12)
        path.lineTo(-3.2, 4.5)
        path.lineTo(-17, 8)
        path.lineTo(-17, 5)
        path.lineTo(-3.2, -4)
        path.closeSubpath()
        p.setPen(QPen(T.C["cyan"], 1.2))
        p.setBrush(QBrush(QColor(34, 211, 238, 60)))
        p.drawPath(path)
        p.restore()

        # vector de viento
        wd, ws = st.get("wd"), st.get("ws")
        if wd is not None and ws:
            a = math.radians(wd - ref + 90)  # de dónde viene -> flecha hacia el centro
            ox = cx + math.cos(a) * (rad - 44)
            oy = cy + math.sin(a) * (rad - 44)
            ix = cx + math.cos(a) * (rad - 74)
            iy = cy + math.sin(a) * (rad - 74)
            p.setPen(QPen(T.C["green"], 1.8))
            p.drawLine(QPointF(ox, oy), QPointF(ix, iy))
            ang = math.atan2(iy - oy, ix - ox)
            for s in (+1, -1):
                p.drawLine(QPointF(ix, iy),
                           QPointF(ix - math.cos(ang + s * 0.5) * 7,
                                   iy - math.sin(ang + s * 0.5) * 7))
            _f(p, 8, QFont.Weight.Bold)
            p.setPen(QPen(T.C["green"]))
            p.drawText(QRectF(r.left() + 10, r.bottom() - 36, 120, 14),
                       Qt.AlignmentFlag.AlignLeft, f"WIND {int(wd):03d}/{int(ws)}")

        # indicador de alabeo
        roll = st.get("roll")
        if roll is not None:
            bw = 54
            bx = r.right() - bw - 12
            by = r.top() + 10
            p.setPen(QPen(QColor("#27394c"), 1))
            p.drawLine(QPointF(bx, by + 10), QPointF(bx + bw, by + 10))
            px = bx + bw / 2 + max(-1, min(1, roll / 30)) * (bw / 2 - 3)
            p.setPen(QPen(T.C["amber"], 2))
            p.setBrush(QBrush(T.C["amber"]))
            p.drawPolygon(QPolygonF([QPointF(px, by + 6), QPointF(px - 4, by + 13),
                                     QPointF(px + 4, by + 13)]))
            _f(p, 7, QFont.Weight.Medium)
            p.setPen(QPen(T.C["muted"]))
            p.drawText(QRectF(bx - 6, by - 4, bw + 12, 10),
                       Qt.AlignmentFlag.AlignCenter, f"ROLL {roll:+.0f}°")

        # lecturas TRK / HDG / GS
        _f(p, 9, QFont.Weight.Bold)
        p.setPen(QPen(T.C["cyan"]))
        p.drawText(QRectF(cx - 60, cy - rad - 26, 120, 16),
                   Qt.AlignmentFlag.AlignCenter,
                   f"TRK {trk:05.1f}°" if trk is not None else "TRK ---")
        p.setPen(QPen(T.C["muted"]))
        txt = []
        if mhdg is not None:
            txt.append(f"HDG {mhdg:05.1f}M")
        gs = st.get("gs")
        if gs is not None:
            txt.append(f"GS {int(gs)}")
        p.drawText(QRectF(r.left(), r.bottom() - 20, r.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, "   ".join(txt))


class Field(QFrame):
    """Celda etiqueta/valor."""

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.setObjectName("cardFlat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 6)
        lay.setSpacing(1)
        self.k = QLabel(key)
        self.k.setObjectName("key")
        self.v = QLabel("---")
        self.v.setObjectName("value")
        self.v.setFont(T.mono(11, QFont.Weight.Bold))
        lay.addWidget(self.k)
        lay.addWidget(self.v)

    def set(self, val, color=None):
        self.v.setText("---" if val is None else str(val))
        self.v.setStyleSheet(f"color:{color or T.WHITE};")


class DataGrid(QFrame):
    """Grilla con todos los parámetros extra que publica la fuente ADS-B."""

    SPEC = [
        ("GS", "gs", "{:.0f} kt", T.CYAN),
        ("IAS", "ias", "{:.0f} kt", T.WHITE),
        ("TAS", "tas", "{:.0f} kt", T.WHITE),
        ("MACH", "mach", "{:.3f}", T.CYAN),
        ("ALT BARO", "alt_baro", "{} ft", T.GREEN),
        ("ALT GEOM", "alt_geom", "{} ft", T.WHITE),
        ("V/S BARO", "baro_rate", "{:+.0f} fpm", T.AMBER),
        ("V/S GEOM", "geom_rate", "{:+.0f} fpm", T.MUTED),
        ("TRACK", "track", "{:.1f}°", T.CYAN),
        ("HDG MAG", "mag_heading", "{:.1f}°", T.WHITE),
        ("HDG TRUE", "true_heading", "{:.1f}°", T.MUTED),
        ("TRK RATE", "track_rate", "{:+.2f}°/s", T.MUTED),
        ("ROLL", "roll", "{:+.1f}°", T.AMBER),
        ("WIND", "_wind", "{}", T.GREEN),
        ("OAT", "oat", "{:.0f} °C", T.WHITE),
        ("TAT", "tat", "{:.0f} °C", T.MUTED),
        ("QNH SEL", "nav_qnh", "{:.1f} hPa", T.MAGENTA),
        ("ALT SEL", "nav_altitude_mcp", "{} ft", T.MAGENTA),
        ("ALT FMS", "nav_altitude_fms", "{} ft", T.MAGENTA),
        ("HDG SEL", "nav_heading", "{:.1f}°", T.MAGENTA),
        ("SQUAWK", "squawk", "{}", T.AMBER),
        ("EMERG", "emergency", "{}", T.RED),
        ("CATEG", "category", "{}", T.MUTED),
        ("MODE S", "hex", "{}", T.WHITE),
        ("NIC/RC", "_nicrc", "{}", T.MUTED),
        ("NACp/v", "_nac", "{}", T.MUTED),
        ("SIL", "_sil", "{}", T.MUTED),
        ("RSSI", "rssi", "{:.1f} dBFS", T.MUTED),
        ("MSGS", "messages", "{}", T.MUTED),
        ("AGE POS", "seen_pos", "{:.1f} s", T.MUTED),
        ("SRC", "type", "{}", T.BLUE),
        ("LAT/LON", "_ll", "{}", T.WHITE),
    ]

    def __init__(self, cols=4, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)
        title = QLabel("FLIGHT PARAMETERS")
        title.setObjectName("cardTitle")
        outer.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(6)
        outer.addLayout(grid)
        self.fields = {}
        for i, (label, key, fmt, col) in enumerate(self.SPEC):
            f = Field(label)
            self.fields[key] = (f, fmt, col)
            grid.addWidget(f, i // cols, i % cols)

    def set_state(self, st):
        st = st or {}
        derived = {
            "_wind": (f"{int(st['wd']):03d}° / {int(st['ws'])} kt"
                      if st.get("wd") is not None and st.get("ws") is not None else None),
            "_nicrc": (f"{st.get('nic')} / {st.get('rc')} m"
                       if st.get("nic") is not None else None),
            "_nac": (f"{st.get('nac_p')} / {st.get('nac_v')}"
                     if st.get("nac_p") is not None else None),
            "_sil": (f"{st.get('sil')} {st.get('sil_type','')}".strip()
                     if st.get("sil") is not None else None),
            "_ll": (f"{st['lat']:.3f} {st['lon']:.3f}"
                    if st.get("lat") is not None else None),
        }
        for key, (field, fmt, col) in self.fields.items():
            v = derived.get(key, st.get(key))
            if v is None or v == "":
                field.set(None, T.MUTED)
                continue
            if key == "alt_baro" and v == "ground":
                field.set("GROUND", T.AMBER)
                continue
            try:
                txt = fmt.format(v)
            except (ValueError, TypeError):
                txt = str(v)
            c = col
            if key == "emergency" and str(v).lower() == "none":
                c = T.MUTED
            field.set(txt, c)


class CockpitPanel(QFrame):
    """PFD compacto: cinta de velocidad, HSI, cinta de altitud y V/S."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("PRIMARY FLIGHT DISPLAY")
        t.setObjectName("cardTitle")
        self.tgt = QLabel("NO TARGET")
        self.tgt.setObjectName("key")
        self.tgt.setAlignment(Qt.AlignmentFlag.AlignRight)
        head.addWidget(t)
        head.addWidget(self.tgt)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.spd = Tape("spd")
        self.hsi = HSI()
        self.alt = Tape("alt")
        self.vsi = VSI()
        row.addWidget(self.spd, 2)
        row.addWidget(self.hsi, 5)
        row.addWidget(self.alt, 2)
        row.addWidget(self.vsi, 1)
        lay.addLayout(row)

    def set_state(self, st):
        for w in (self.spd, self.hsi, self.alt, self.vsi):
            w.set_state(st)
        if st:
            cs = (st.get("flight") or "").strip() or "-"
            self.tgt.setText(f"{cs}  ·  {st.get('r') or '?'}  ·  {st.get('t') or '?'}")
            self.tgt.setStyleSheet(f"color:{T.CYAN};")
        else:
            self.tgt.setText("NO TARGET")
            self.tgt.setStyleSheet(f"color:{T.MUTED};")
