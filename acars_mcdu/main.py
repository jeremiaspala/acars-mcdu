#!/usr/bin/env python3
"""ACARS MCDU — terminal ACARS de cabina + mapa + parámetros de vuelo en vivo.

Fuente de mensajes: acarsdec (RTL-SDR), por UDP JSON (-j) o proceso propio (-o 4).
Datos del avión: api.adsb.lol (estado en vivo) y api.adsbdb.com (matrícula/ruta).
"""

import argparse
import signal
import sys
import time
from collections import deque

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout,
                             QLabel, QPushButton, QSplitter, QVBoxLayout,
                             QWidget)

from . import config
from . import theme as T
from .instruments import CockpitPanel, DataGrid
from .lookup import AdsbClient
from .mapview import MapView
from .mcdu import MCDU
from .source import AcarsSource
from .sourcedialog import SourceDialog
from .store import Store


class Chip(QLabel):
    def __init__(self, text="", color=T.MUTED, parent=None):
        super().__init__(text, parent)
        self.setFont(T.mono(9, QFont.Weight.Bold))
        self.set_color(color)

    def set_color(self, color):
        self.setStyleSheet(
            f"color:{color}; background: rgba(255,255,255,0.03);"
            f"border:1px solid {T.BORDER}; border-radius:8px; padding:4px 9px;")


class IdentCard(QFrame):
    """Identificación del avión + foto (adsbdb)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)
        self.photo = QLabel()
        self.photo.setFixedSize(132, 88)
        self.photo.setStyleSheet(
            f"background:{T.SURFACE_2}; border:1px solid {T.BORDER};"
            "border-radius:8px; color:" + T.MUTED + ";")
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setText("NO IMAGE")
        self.photo.setFont(T.mono(8))
        txt = QVBoxLayout()
        txt.setSpacing(2)
        t = QLabel("AIRCRAFT")
        t.setObjectName("cardTitle")
        self.reg = QLabel("--")
        self.reg.setObjectName("valueBig")
        self.reg.setFont(T.mono(17, QFont.Weight.Bold))
        self.typ = QLabel("")
        self.op = QLabel("")
        self.rt = QLabel("")
        for lb, col, sz in ((self.typ, T.WHITE, 11), (self.op, T.MUTED, 10),
                            (self.rt, T.GREEN, 11)):
            lb.setFont(T.mono(sz, QFont.Weight.Medium))
            lb.setStyleSheet(f"color:{col};")
        txt.addWidget(t)
        txt.addWidget(self.reg)
        txt.addWidget(self.typ)
        txt.addWidget(self.op)
        txt.addWidget(self.rt)
        txt.addStretch(1)
        lay.addWidget(self.photo)
        lay.addLayout(txt, 1)

    def set_info(self, info, live):
        info = info or {}
        live = live or {}
        self.reg.setText(info.get("registration") or live.get("r") or "--")
        self.typ.setText(((info.get("manufacturer", "") + " " +
                           info.get("type", "")).strip()
                          or live.get("t") or "").upper() or "TIPO DESCONOCIDO")
        self.op.setText((info.get("registered_owner") or "OPERADOR DESCONOCIDO")
                        + "  ·  " + (info.get("mode_s") or
                                     (live.get("hex") or "").upper()))

    def set_route(self, rt):
        if not rt:
            self.rt.setText("")
            return
        o = (rt.get("origin") or {})
        d = (rt.get("destination") or {})
        self.rt.setText(f"{o.get('iata_code','---')} {o.get('municipality','')}"
                        f"  →  {d.get('iata_code','---')} {d.get('municipality','')}")

    def set_photo(self, data):
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.photo.setPixmap(pm.scaled(
                self.photo.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.photo.setText("NO IMAGE")


class Window(QWidget):
    def __init__(self, cfg, args):
        super().__init__()
        self.cfg = cfg
        self.args = args
        self.setWindowTitle("ACARS MCDU · RTL-SDR")
        self.resize(1700, 980)

        self.store = Store()
        self.api = AdsbClient(self.store, self)
        self.src = AcarsSource(cfg, self)

        self.target_reg = None
        self.target_hex = None
        self.target_cs = None
        self.reg_to_hex = {}
        self.chan_counts = {}
        self.session = 0
        self.recent_ts = deque(maxlen=500)
        self.last_status = "arrancando"
        self.api_state = "---"
        self.auto = True

        # ---------- layout ----------
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(8)
        self.mcdu = MCDU(self.store)
        self.mcdu.setMinimumWidth(430)
        split.addWidget(self.mcdu)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setHandleWidth(8)
        self.map = MapView(cfg)
        vsplit.addWidget(self.map)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        self.pfd = CockpitPanel()
        bl.addWidget(self.pfd, 4)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.ident = IdentCard()
        self.grid = DataGrid(cols=4)
        col.addWidget(self.ident)
        col.addWidget(self.grid, 1)
        bl.addLayout(col, 5)
        vsplit.addWidget(bottom)
        vsplit.setSizes([430, 500])
        rl.addWidget(vsplit)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([520, 1180])
        root.addWidget(split, 1)
        root.insertLayout(0, self._build_header())

        # ---------- señales ----------
        self.src.message.connect(self.on_acars)
        self.src.status.connect(self.on_src_status)
        self.api.traffic.connect(self.on_traffic)
        self.api.target.connect(self.on_target)
        self.api.ac_info.connect(self.on_acinfo)
        self.api.route_info.connect(self.on_route)
        self.api.photo.connect(lambda reg, data: self.ident.set_photo(data))
        self.api.error.connect(self.on_api_err)
        self.map.selected.connect(self.select_hex)
        self.mcdu.track_request.connect(self.track_tail)

        # ---------- fuente ----------
        self.src.mode_changed.connect(lambda m: self.tick())
        self.src.start(cfg["source"]["mode"])

        self.mcdu.msgs = self.store.recent(400)
        self.mcdu.set_sysinfo(freqs=cfg["acarsdec"]["freqs"],
                              gain=cfg["acarsdec"]["gain"],
                              station=f"{cfg['station']['name']} "
                                      f"{cfg['station']['lat']:.3f} "
                                      f"{cfg['station']['lon']:.3f}",
                              chan_counts=self.chan_counts)
        self.mcdu.refresh()

        # ---------- timers ----------
        p = cfg["poll"]
        self.t_traffic = QTimer(self, interval=int(p["traffic_sec"]) * 1000)
        self.t_traffic.timeout.connect(self.poll_traffic)
        self.t_traffic.start()
        self.poll_traffic()
        self.t_target = QTimer(self, interval=int(p["target_sec"]) * 1000)
        self.t_target.timeout.connect(self.poll_target)
        self.t_target.start()
        self.t_ui = QTimer(self, interval=1000)
        self.t_ui.timeout.connect(self.tick)
        self.t_ui.start()

    # ---------- header ----------
    def _build_header(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        title = QLabel("ACARS  ·  MCDU")
        title.setFont(T.mono(15, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{T.CYAN}; letter-spacing:3px;")
        bar.addWidget(title)

        self.c_src = Chip("SRC —")
        self.c_src.setToolTip("Click en SOURCE para cambiar de fuente")
        self.c_rate = Chip("0.0 MSG/MIN")
        self.c_cnt = Chip("0 MSGS")
        self.c_tgt = Chip("NO TARGET", T.MUTED)
        self.c_api = Chip("API —")
        for c in (self.c_src, self.c_rate, self.c_cnt, self.c_tgt, self.c_api):
            bar.addWidget(c)
        bar.addStretch(1)

        b_src = QPushButton("SOURCE")
        b_src.setObjectName("accent")
        b_src.clicked.connect(self.choose_source)
        bar.addWidget(b_src)
        self.b_stop = QPushButton("STOP")
        self.b_stop.clicked.connect(self.toggle_source)
        bar.addWidget(self.b_stop)

        self.b_auto = QPushButton("AUTO TARGET")
        self.b_auto.setCheckable(True)
        self.b_auto.setChecked(True)
        self.b_auto.toggled.connect(lambda v: setattr(self, "auto", v))
        b_follow = QPushButton("FOLLOW")
        b_follow.setCheckable(True)
        b_follow.setChecked(True)
        b_follow.toggled.connect(lambda v: setattr(self.map, "follow", v))
        b_home = QPushButton("STATION")
        b_home.clicked.connect(self.map.recenter_station)
        b_zi = QPushButton("+")
        b_zi.clicked.connect(lambda: self._zoom(1))
        b_zo = QPushButton("−")
        b_zo.clicked.connect(lambda: self._zoom(-1))
        for b in (self.b_auto, b_follow, b_home, b_zo, b_zi):
            bar.addWidget(b)
        return bar

    # ---------- fuente ----------
    def choose_source(self):
        dlg = SourceDialog(self.cfg, self.src.mode, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.cfg = dlg.result_config()
        config.save(self.cfg)
        self.src.cfg = self.cfg
        self.src.start(self.cfg["source"]["mode"])
        self.chan_counts.clear()
        self.mcdu.set_sysinfo(freqs=self.cfg["acarsdec"]["freqs"],
                              gain=self.cfg["acarsdec"]["gain"],
                              chan_counts=self.chan_counts)
        self.tick()

    def toggle_source(self):
        if self.src.mode == "OFF":
            self.src.start(self.cfg["source"]["mode"])
        else:
            self.src.stop()
            self.last_status = "fuente detenida por el usuario"
        self.tick()

    def _zoom(self, d):
        self.map.zoom = max(2, min(14, self.map.zoom + d))
        self.map.update()

    # ---------- ACARS ----------
    def on_acars(self, msg):
        row = self.store.get(self.store.add_message(msg))
        if row is None:
            return
        self.session += 1
        self.recent_ts.append(time.time())
        ch = msg.get("channel")
        if ch is not None:
            self.chan_counts[ch] = self.chan_counts.get(ch, 0) + 1
        self.mcdu.on_message(row)

        reg = (row.get("tail") or "").upper()
        cs = (row.get("flight") or "").upper()
        if reg:
            self.api.fetch_aircraft(reg)
            h = self.reg_to_hex.get(reg)
            if h:
                self.map.mark_acars(h)
            else:
                self.api.track(reg=reg)
        if cs:
            self.api.fetch_route(cs)
        if self.auto and reg:
            self.track_tail(reg, cs)

    def on_src_status(self, txt):
        self.last_status = txt

    # ---------- selección de objetivo ----------
    def track_tail(self, reg, callsign=""):
        reg = (reg or "").upper()
        self.target_reg = reg
        self.target_cs = (callsign or "").upper() or None
        self.target_hex = self.reg_to_hex.get(reg)
        self.api.fetch_aircraft(reg)
        if self.target_cs:
            self.api.fetch_route(self.target_cs)
        if self.target_hex:
            self.map.select(self.target_hex)
            self.api.track(hexid=self.target_hex)
        else:
            self.api.track(reg=reg)
        self.c_tgt.setText(reg)
        self.c_tgt.set_color(T.AMBER)

    def select_hex(self, hexid):
        self.target_hex = hexid
        a = self.map.traffic.get(hexid, {})
        reg = (a.get("r") or "").upper()
        cs = (a.get("flight") or "").strip().upper()
        self.target_reg = reg or None
        self.target_cs = cs or None
        if reg:
            self.reg_to_hex[reg] = hexid
            self.api.fetch_aircraft(reg)
        if cs:
            self.api.fetch_route(cs)
        self.api.track(hexid=hexid)
        self.on_target(a)
        self.c_tgt.setText(reg or cs or hexid.upper())
        self.c_tgt.set_color(T.AMBER)

    # ---------- datos en vivo ----------
    def on_traffic(self, items):
        self.api_state = "OK"
        for a in items:
            reg = (a.get("r") or "").upper()
            if reg:
                self.reg_to_hex[reg] = (a.get("hex") or "").lower()
        self.map.set_traffic(items)
        if self.target_reg and not self.target_hex:
            h = self.reg_to_hex.get(self.target_reg)
            if h:
                self.target_hex = h
                self.map.select(h)

    def on_target(self, a):
        if not a:
            return
        self.api_state = "OK"
        h = (a.get("hex") or "").lower()
        reg = (a.get("r") or "").upper()
        if reg:
            self.reg_to_hex[reg] = h
        if self.target_reg and reg and reg != self.target_reg:
            return
        self.target_hex = h or self.target_hex
        self.map.set_target(a)
        self.pfd.set_state(a)
        self.grid.set_state(a)
        self.mcdu.set_live(a)
        self.ident.set_info(self.mcdu.acinfo, a)

    def on_acinfo(self, reg, info):
        if reg == (self.target_reg or reg):
            self.mcdu.set_acinfo(info)
            self.ident.set_info(info, self.mcdu.live)
        h = (info.get("mode_s") or "").lower()
        if h:
            self.reg_to_hex[reg] = h
            if reg == self.target_reg:
                self.target_hex = h
                self.map.select(h)
            self.map.mark_acars(h)

    def on_route(self, cs, rt):
        if self.target_cs in (None, cs):
            self.mcdu.set_route(rt)
            self.ident.set_route(rt)

    def on_api_err(self, txt):
        self.api_state = "ERR"
        self.last_status = txt

    def poll_traffic(self):
        s = self.cfg["station"]
        self.api.poll_traffic(s["lat"], s["lon"], self.cfg["poll"]["radius_nm"])

    def poll_target(self):
        if self.target_hex:
            self.api.track(hexid=self.target_hex)
        elif self.target_reg:
            self.api.track(reg=self.target_reg)
        elif self.target_cs:
            self.api.track(callsign=self.target_cs)

    # ---------- reloj / estado ----------
    def tick(self):
        now = time.time()
        while self.recent_ts and now - self.recent_ts[0] > 600:
            self.recent_ts.popleft()
        rate = len(self.recent_ts) / 10.0
        total = self.store.count()
        live = self.src.mode not in ("OFF", "ERROR")
        self.c_src.setText(f"SRC {self.src.mode}" +
                           (f" · {self.src.detail}" if self.src.detail else ""))
        self.c_src.set_color(T.GREEN if live else
                             (T.RED if self.src.mode == "ERROR" else T.MUTED))
        self.b_stop.setText("STOP" if live else "START")
        self.c_rate.setText(f"{rate:.1f} MSG/MIN")
        self.c_cnt.setText(f"{total} MSGS · {self.session} SES")
        self.c_api.setText(f"API {self.api_state}")
        self.c_api.set_color(T.GREEN if self.api_state == "OK" else T.AMBER)
        self.mcdu.set_sysinfo(
            mode=self.src.mode, detail=self.src.detail,
            online=self.api_state == "OK", total=total,
            session=self.session, rate=rate, traffic=len(self.map.traffic),
            heard=len(self.map.acars_hex), api=self.api_state,
            last_status=self.last_status, chan_counts=self.chan_counts)
        if self.mcdu.page in ("STATUS", "ATC"):
            self.mcdu.refresh()

    def closeEvent(self, ev):
        for t in (self.t_traffic, self.t_target, self.t_ui):
            t.stop()
        self.src.stop()
        super().closeEvent(ev)
        QApplication.instance().quit()


def main():
    ap = argparse.ArgumentParser(description="ACARS MCDU (RTL-SDR + Qt)")
    ap.add_argument("--source", choices=["rtl", "udp", "cmd", "sim"],
                    help="fuente de mensajes (si se omite, la última guardada)")
    ap.add_argument("--spawn", action="store_true",
                    help="alias de --source rtl")
    ap.add_argument("--command", help="comando externo para --source cmd")
    ap.add_argument("--device", help="índice o S/N del dongle RTL-SDR")
    ap.add_argument("--gain", type=float)
    ap.add_argument("--ppm", type=int)
    ap.add_argument("--freqs", nargs="+", type=float, help="frecuencias en MHz")
    ap.add_argument("--port", type=int, help="puerto UDP de escucha")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    args = ap.parse_args()

    cfg = config.load()
    if args.source:
        cfg["source"]["mode"] = args.source
    elif args.spawn:
        cfg["source"]["mode"] = "rtl"
    if args.command:
        cfg["source"]["command"] = args.command
        cfg["source"]["mode"] = args.source or "cmd"
    if args.device:
        cfg["acarsdec"]["device"] = args.device
    if args.gain is not None:
        cfg["acarsdec"]["gain"] = args.gain
    if args.ppm is not None:
        cfg["acarsdec"]["ppm"] = args.ppm
    if args.freqs:
        cfg["acarsdec"]["freqs"] = args.freqs
    if args.port:
        cfg["udp"]["port"] = args.port
    if args.lat is not None:
        cfg["station"]["lat"] = args.lat
    if args.lon is not None:
        cfg["station"]["lon"] = args.lon

    app = QApplication(sys.argv)
    app.setApplicationName("ACARS MCDU")
    app.setStyleSheet(T.QSS)
    w = Window(cfg, args)
    w.show()

    # cerrar acarsdec aunque nos manden SIGTERM/SIGINT (si no, queda huérfano
    # tomando el dongle)
    app.aboutToQuit.connect(w.src.stop)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: app.quit())
    timer = QTimer(app, interval=400)   # deja correr el loop de python
    timer.timeout.connect(lambda: None)
    timer.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
