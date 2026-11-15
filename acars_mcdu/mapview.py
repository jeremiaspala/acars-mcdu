"""Mapa deslizante propio (sin WebEngine): tiles raster + capa de tráfico."""

import math
import os
from collections import OrderedDict, deque

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QSizePolicy

from . import config
from . import theme as T

TILE = 256
MAX_INFLIGHT = 10


def ll_to_world(lat, lon, z):
    n = TILE * (2 ** z)
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def world_to_ll(x, y, z):
    n = TILE * (2 ** z)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


class MapView(QFrame):
    selected = pyqtSignal(str)   # hex ICAO

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.cfg = cfg
        self.zoom = int(cfg["map"]["zoom"])
        self.station = (cfg["station"]["lat"], cfg["station"]["lon"])
        self.center = list(self.station)
        self.layers = [cfg["map"]["tiles"]]
        if cfg["map"].get("overlay"):
            self.layers.append(cfg["map"]["overlay"])
        self.rings = cfg["map"]["range_rings_nm"]

        self.traffic = {}          # hex -> dict estado
        self.trails = {}           # hex -> deque[(lat,lon)]
        self.acars_hex = set()     # aviones de los que oímos ACARS
        self.sel_hex = None
        self.follow = True

        self._mem = OrderedDict()
        self._nam = QNetworkAccessManager(self)
        self._inflight = set()
        self._drag = None

    # ---- datos -----------------------------------------------------------
    def set_traffic(self, items):
        for a in items:
            h = (a.get("hex") or "").lower()
            if not h or a.get("lat") is None:
                continue
            old = self.traffic.get(h, {})
            old.update(a)
            self.traffic[h] = old
            tr = self.trails.setdefault(h, deque(maxlen=120))
            if not tr or tr[-1] != (a["lat"], a["lon"]):
                tr.append((a["lat"], a["lon"]))
        self.update()

    def set_target(self, a):
        h = (a.get("hex") or "").lower()
        if h:
            self.set_traffic([a])
            self.sel_hex = h
            if self.follow and a.get("lat") is not None:
                self.center = [a["lat"], a["lon"]]
        self.update()

    def mark_acars(self, hexid):
        if hexid:
            self.acars_hex.add(hexid.lower())
            self.update()

    def select(self, hexid):
        self.sel_hex = (hexid or "").lower() or None
        self.update()

    def recenter_station(self):
        self.center = list(self.station)
        self.update()

    # ---- tiles -----------------------------------------------------------
    def _tile(self, z, x, y, layer=0):
        key = (layer, z, x, y)
        pm = self._mem.get(key)
        if pm is not None:
            self._mem.move_to_end(key)
            return pm
        path = os.path.join(config.TILE_DIR, f"l{layer}", str(z), str(x), f"{y}.tile")
        if os.path.exists(path):
            pm = QPixmap()
            try:
                with open(path, "rb") as fh:
                    if pm.loadFromData(fh.read()):
                        self._put(key, pm)
                        return pm
            except OSError:
                pass
        self._fetch(z, x, y, layer, path)
        return None

    def _put(self, key, pm):
        self._mem[key] = pm
        while len(self._mem) > 600:
            self._mem.popitem(last=False)

    def _fetch(self, z, x, y, layer, path):
        key = (layer, z, x, y)
        if key in self._inflight or len(self._inflight) >= MAX_INFLIGHT:
            return
        url = self.layers[layer].format(z=z, x=x, y=y)
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.USER_AGENT.encode())
        self._inflight.add(key)
        rep = self._nam.get(req)

        def done():
            try:
                self._inflight.discard(key)
                data = bytes(rep.readAll())
                ok = rep.error().value == 0
                rep.deleteLater()
                if not ok or not data:
                    return
                pm = QPixmap()
                if pm.loadFromData(data):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    try:
                        with open(path, "wb") as fh:
                            fh.write(data)
                    except OSError:
                        pass
                    self._put(key, pm)
                    self.update()
            except RuntimeError:
                pass   # el widget se destruyó mientras bajaba el tile

        rep.finished.connect(done)

    # ---- proyección ------------------------------------------------------
    def _origin(self):
        cx, cy = ll_to_world(self.center[0], self.center[1], self.zoom)
        return cx - self.width() / 2, cy - self.height() / 2

    def to_px(self, lat, lon):
        ox, oy = self._origin()
        x, y = ll_to_world(lat, lon, self.zoom)
        return QPointF(x - ox, y - oy)

    def to_ll(self, px, py):
        ox, oy = self._origin()
        return world_to_ll(ox + px, oy + py, self.zoom)

    # ---- pintado ---------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor("#060a0f"))

        ox, oy = self._origin()
        n = 2 ** self.zoom
        tx0 = int(math.floor(ox / TILE))
        ty0 = int(math.floor(oy / TILE))
        tx1 = int(math.floor((ox + self.width()) / TILE))
        ty1 = int(math.floor((oy + self.height()) / TILE))
        for layer in range(len(self.layers)):
            for tx in range(tx0, tx1 + 1):
                for ty in range(ty0, ty1 + 1):
                    if ty < 0 or ty >= n:
                        continue
                    pm = self._tile(self.zoom, tx % n, ty, layer)
                    dx = tx * TILE - ox
                    dy = ty * TILE - oy
                    if pm is None:
                        if layer == 0:
                            p.setPen(QPen(QColor("#0d141c"), 1))
                            p.setBrush(QBrush(QColor("#080d13")))
                            p.drawRect(QRectF(dx, dy, TILE, TILE))
                    else:
                        p.drawPixmap(QRectF(dx, dy, TILE, TILE), pm,
                                     QRectF(0, 0, pm.width(), pm.height()))

        self._draw_station(p)
        self._draw_traffic(p)
        self._draw_chrome(p)

    def _draw_station(self, p):
        c = self.to_px(*self.station)
        mpp = 156543.03392 * math.cos(math.radians(self.center[0])) / (2 ** self.zoom)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(T.mono(7, QFont.Weight.Medium))
        for nm in self.rings:
            r = nm * 1852.0 / mpp
            if r < 14 or r > max(self.width(), self.height()) * 1.6:
                continue
            p.setPen(QPen(QColor(34, 211, 238, 42), 1, Qt.PenStyle.DashLine))
            p.drawEllipse(c, r, r)
            p.setPen(QPen(QColor(34, 211, 238, 110)))
            p.drawText(QRectF(c.x() - 20, c.y() - r - 12, 40, 12),
                       Qt.AlignmentFlag.AlignCenter, f"{nm}")
        p.setPen(QPen(T.C["cyan"], 1.6))
        p.setBrush(QBrush(QColor(34, 211, 238, 70)))
        p.drawEllipse(c, 4.5, 4.5)
        p.setPen(QPen(T.C["cyan"], 1.2))
        p.drawLine(QPointF(c.x(), c.y() - 11), QPointF(c.x(), c.y() - 5))
        p.setFont(T.mono(7, QFont.Weight.Bold))
        p.drawText(QRectF(c.x() + 8, c.y() - 6, 120, 12),
                   Qt.AlignmentFlag.AlignLeft, self.cfg["station"]["name"])

    def _plane_path(self, s=1.0):
        pt = QPainterPath()
        pts = [(0, -9), (1.9, -2.4), (10, 2.6), (10, 4.4), (1.9, 2.4), (1.6, 7),
               (4.2, 9.4), (4.2, 10.6), (0, 9.2), (-4.2, 10.6), (-4.2, 9.4),
               (-1.6, 7), (-1.9, 2.4), (-10, 4.4), (-10, 2.6), (-1.9, -2.4)]
        pt.moveTo(pts[0][0] * s, pts[0][1] * s)
        for x, y in pts[1:]:
            pt.lineTo(x * s, y * s)
        pt.closeSubpath()
        return pt

    def _draw_traffic(self, p):
        # estelas
        for h, tr in self.trails.items():
            if len(tr) < 2:
                continue
            sel = h == self.sel_hex
            if not sel and h not in self.acars_hex:
                continue
            p.setPen(QPen(QColor(255, 176, 46, 150) if sel else QColor(34, 211, 238, 70),
                          1.8 if sel else 1.2))
            prev = None
            for lat, lon in tr:
                cur = self.to_px(lat, lon)
                if prev is not None:
                    p.drawLine(prev, cur)
                prev = cur

        for h, a in self.traffic.items():
            if a.get("lat") is None:
                continue
            pos = self.to_px(a["lat"], a["lon"])
            if not (-40 <= pos.x() <= self.width() + 40 and
                    -40 <= pos.y() <= self.height() + 40):
                continue
            sel = h == self.sel_hex
            heard = h in self.acars_hex
            col = T.C["amber"] if sel else (T.C["cyan"] if heard else QColor("#6b8ba8"))
            trk = a.get("track") or a.get("true_heading") or 0
            p.save()
            p.translate(pos)
            p.rotate(trk)
            p.setPen(QPen(col, 1.3))
            p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(),
                                     150 if (sel or heard) else 70)))
            p.drawPath(self._plane_path(1.25 if sel else 1.0))
            p.restore()
            if sel:
                p.setPen(QPen(QColor(255, 176, 46, 120), 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(pos, 18, 18)
            if sel or heard:
                cs = (a.get("flight") or "").strip() or (a.get("r") or h.upper())
                alt = a.get("alt_baro")
                alt_s = "GND" if alt == "ground" else (
                    f"{int(alt)//100:03d}" if isinstance(alt, (int, float)) else "---")
                gs = a.get("gs")
                lbl = f"{cs}  FL{alt_s}" + (f"  {int(gs)}" if gs else "")
                p.setFont(T.mono(7, QFont.Weight.Bold))
                w = 9 + len(lbl) * 5.4
                box = QRectF(pos.x() + 13, pos.y() - 7, w, 14)
                p.setBrush(QBrush(QColor(6, 10, 15, 200)))
                p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 90), 1))
                p.drawRoundedRect(box, 4, 4)
                p.setPen(QPen(col))
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, lbl)

    def _draw_chrome(self, p):
        # barra de escala
        mpp = 156543.03392 * math.cos(math.radians(self.center[0])) / (2 ** self.zoom)
        for nm in (1, 2, 5, 10, 20, 50, 100, 200, 500):
            px = nm * 1852 / mpp
            if px > 70:
                break
        p.setPen(QPen(T.C["muted"], 1.4))
        y = self.height() - 16
        p.drawLine(QPointF(14, y), QPointF(14 + px, y))
        p.drawLine(QPointF(14, y - 4), QPointF(14, y + 4))
        p.drawLine(QPointF(14 + px, y - 4), QPointF(14 + px, y + 4))
        p.setFont(T.mono(7, QFont.Weight.Medium))
        p.drawText(QRectF(14, y - 18, px + 40, 12),
                   Qt.AlignmentFlag.AlignLeft, f"{nm} NM")

        hud = (f"Z{self.zoom}  {self.center[0]:+.3f} {self.center[1]:+.3f}  "
               f"AC {len(self.traffic)}  ACARS {len(self.acars_hex)}"
               f"{'  FOLLOW' if self.follow and self.sel_hex else ''}")
        p.setFont(T.mono(7, QFont.Weight.Bold))
        box = QRectF(self.width() - 10 - (len(hud) * 5.3 + 14), 10,
                     len(hud) * 5.3 + 14, 16)
        p.setBrush(QBrush(QColor(6, 10, 15, 190)))
        p.setPen(QPen(QColor(31, 43, 56), 1))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QPen(T.C["muted"]))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, hud)

    # ---- interacción -----------------------------------------------------
    def wheelEvent(self, ev):
        d = ev.angleDelta().y()
        if not d:
            return
        pos = ev.position()
        lat0, lon0 = self.to_ll(pos.x(), pos.y())
        nz = max(2, min(14, self.zoom + (1 if d > 0 else -1)))
        if nz == self.zoom:
            return
        self.zoom = nz
        # mantener el punto bajo el cursor
        ox, oy = ll_to_world(lat0, lon0, nz)
        cx = ox - (pos.x() - self.width() / 2)
        cy = oy - (pos.y() - self.height() / 2)
        self.center = list(world_to_ll(cx, cy, nz))
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = (ev.position(), list(self.center))

    def mouseMoveEvent(self, ev):
        if self._drag:
            p0, c0 = self._drag
            dx = ev.position().x() - p0.x()
            dy = ev.position().y() - p0.y()
            if abs(dx) + abs(dy) > 3:
                self.follow = False
            cx, cy = ll_to_world(c0[0], c0[1], self.zoom)
            self.center = list(world_to_ll(cx - dx, cy - dy, self.zoom))
            self.update()

    def mouseReleaseEvent(self, ev):
        was = self._drag
        self._drag = None
        if not was:
            return
        if (abs(ev.position().x() - was[0].x()) + abs(ev.position().y() - was[0].y())) > 4:
            return
        best, bd = None, 1e9
        for h, a in self.traffic.items():
            if a.get("lat") is None:
                continue
            pos = self.to_px(a["lat"], a["lon"])
            d = (pos.x() - ev.position().x()) ** 2 + (pos.y() - ev.position().y()) ** 2
            if d < bd:
                best, bd = h, d
        if best and bd < 400:
            self.sel_hex = best
            self.follow = True
            self.selected.emit(best)
            self.update()

    def mouseDoubleClickEvent(self, ev):
        self.follow = True
        if self.sel_hex and self.sel_hex in self.traffic:
            a = self.traffic[self.sel_hex]
            self.center = [a["lat"], a["lon"]]
        self.update()
