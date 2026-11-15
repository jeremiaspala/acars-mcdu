"""MCDU / CDU ACARS: pantalla de 24x14, teclas LSK y páginas navegables."""

import time

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient,
                         QPainter, QPainterPath, QPen)
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme as T

COLS, ROWS = 24, 14

W = T.WHITE
G = T.GREEN
C = T.CYAN
A = T.AMBER
M = T.MAGENTA
GY = T.MUTED


def pad(left="", right="", width=COLS):
    left, right = str(left), str(right)
    space = width - len(left) - len(right)
    if space < 0:
        left = left[:max(0, width - len(right))]
        space = width - len(left) - len(right)
    return left + " " * max(0, space) + right


def center(txt, width=COLS):
    txt = str(txt)[:width]
    pre = (width - len(txt)) // 2
    return " " * pre + txt


def wrap(txt, width=COLS):
    out = []
    for para in (txt or "").replace("\r", "\n").split("\n"):
        para = para.rstrip()
        if not para:
            out.append("")
            continue
        while len(para) > width:
            cut = para.rfind(" ", 0, width)
            cut = cut if cut > width * 0.5 else width
            out.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        out.append(para)
    return out or [""]


class Display(QWidget):
    """Pantalla del MCDU: 14 filas x 24 columnas, colores por segmento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(360, 300)
        self.rows = [[] for _ in range(ROWS)]

    def set_rows(self, rows):
        self.rows = [r if isinstance(r, list) else [(str(r), W, False)]
                     for r in (rows + [[]] * ROWS)[:ROWS]]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(self.rect())

        path = QPainterPath()
        path.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#05090d"))
        g.setColorAt(1, QColor("#0a1118"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#24323f"), 1))
        p.drawPath(path)
        p.setClipPath(path)

        pad_x, pad_y = 14, 10
        inner = r.adjusted(pad_x, pad_y, -pad_x, -pad_y)

        # tamaño de fuente que hace calzar 24 columnas
        size = 6.0
        big = T.mono(10, QFont.Weight.DemiBold)
        for s in range(6, 40):
            f = T.mono(s, QFont.Weight.DemiBold)
            fm = QFontMetricsF(f)
            if fm.horizontalAdvance("M" * COLS) > inner.width() or \
                    fm.height() * ROWS > inner.height():
                break
            size, big = s, f
        fm = QFontMetricsF(big)
        chw = fm.horizontalAdvance("M")
        rowh = inner.height() / ROWS
        small = T.mono(max(6, int(size * 0.72)), QFont.Weight.Medium)

        for i, segs in enumerate(self.rows):
            y = inner.top() + i * rowh
            col = 0
            for seg in segs:
                txt, color, sml = (seg + (False,))[:3] if len(seg) == 2 else seg
                f = small if sml else big
                p.setFont(f)
                p.setPen(QPen(QColor(color)))
                sfm = QFontMetricsF(f)
                x = inner.left() + col * chw
                p.drawText(QRectF(x, y, inner.width() - col * chw, rowh),
                           int(Qt.AlignmentFlag.AlignLeft |
                               Qt.AlignmentFlag.AlignVCenter), txt)
                col += len(txt) if not sml else max(1, int(
                    sfm.horizontalAdvance(txt) / chw))

        # brillo sutil de pantalla
        gl = QLinearGradient(r.topLeft(), r.bottomLeft())
        gl.setColorAt(0, QColor(255, 255, 255, 10))
        gl.setColorAt(0.35, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gl))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)


class MCDU(QFrame):
    track_request = pyqtSignal(str, str)   # (matrícula, callsign)
    page_changed = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.store = store
        self.page = "INDEX"
        self.scratch = ""
        self.msg_offset = 0
        self.det_offset = 0
        self.sel_msg = None
        self.msgs = []
        self.live = {}
        self.acinfo = {}
        self.route = {}
        self.sysinfo = {}
        self.sent = []
        self.ann = {"MSG": False}
        self._lsk = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        ttl = QLabel("ACARS MCDU")
        ttl.setObjectName("cardTitle")
        self.ind = QLabel("")
        self.ind.setObjectName("key")
        self.ind.setAlignment(Qt.AlignmentFlag.AlignRight)
        head.addWidget(ttl)
        head.addWidget(self.ind)
        lay.addLayout(head)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        self.left_keys, self.right_keys = [], []
        lcol = QVBoxLayout()
        lcol.setSpacing(4)
        rcol = QVBoxLayout()
        rcol.setSpacing(4)
        for i in range(6):
            for side, col, lst in (("L", lcol, self.left_keys),
                                   ("R", rcol, self.right_keys)):
                b = QPushButton(f"{side}{i+1}" if side == "L" else f"{i+1}{side}")
                b.setObjectName("lsk")
                b.clicked.connect(lambda _, s=side, n=i: self._lsk_press(s, n))
                col.addWidget(b)
                lst.append(b)
        self.disp = Display()
        mid.addLayout(lcol)
        mid.addWidget(self.disp, 1)
        mid.addLayout(rcol)
        lay.addLayout(mid, 1)

        # teclas de página
        pg = QGridLayout()
        pg.setSpacing(4)
        pages = [("INDEX", "INDEX"), ("MSG LOG", "MSGLOG"), ("FLT DATA", "FLTDATA"),
                 ("A/C DATA", "ACDATA"), ("RADIO", "RADIO"), ("STATUS", "STATUS"),
                 ("DOWNLINK", "SEND"), ("ATC RPT", "ATC")]
        for i, (lbl, key) in enumerate(pages):
            b = QPushButton(lbl)
            b.setObjectName("page")
            b.clicked.connect(lambda _, k=key: self.goto(k))
            pg.addWidget(b, i // 4, i % 4)
        lay.addLayout(pg)

        # teclado
        kp = QGridLayout()
        kp.setSpacing(3)
        keys = ("ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ/+-.", "1234567890")
        for rw, row in enumerate(keys):
            for cl, ch in enumerate(row):
                b = QPushButton(ch)
                b.setObjectName("kp")
                b.clicked.connect(lambda _, c=ch: self._type(c))
                kp.addWidget(b, rw, cl)
        extra = [("SP", lambda: self._type(" ")), ("CLR", self._clr),
                 ("▲ UP", lambda: self._scroll(-1)), ("▼ DN", lambda: self._scroll(1)),
                 ("OVFY", lambda: self._type("∆")), ("MENU", lambda: self.goto("INDEX"))]
        for i, (lbl, fn) in enumerate(extra):
            b = QPushButton(lbl)
            b.setObjectName("kp")
            b.clicked.connect(lambda _, f=fn: f())
            kp.addWidget(b, 4, i * 2, 1, 2)
        lay.addLayout(kp)

        self.refresh()

    # ---- entradas externas ----------------------------------------------
    def on_message(self, row):
        self.msgs.insert(0, row)
        del self.msgs[400:]
        self.ann["MSG"] = True
        if self.page in ("MSGLOG", "INDEX", "STATUS"):
            self.refresh()

    def set_live(self, st):
        self.live = st or {}
        if self.page in ("FLTDATA", "ACDATA", "INDEX"):
            self.refresh()

    def set_acinfo(self, info):
        self.acinfo = info or {}
        if self.page in ("ACDATA", "INDEX"):
            self.refresh()

    def set_route(self, rt):
        self.route = rt or {}
        if self.page in ("ACDATA", "INDEX"):
            self.refresh()

    def set_sysinfo(self, **kw):
        self.sysinfo.update(kw)
        if self.page in ("STATUS", "RADIO"):
            self.refresh()

    # ---- navegación ------------------------------------------------------
    def goto(self, page):
        self.page = page
        self.det_offset = 0
        if page == "MSGLOG":
            self.ann["MSG"] = False
        self.page_changed.emit(page)
        self.refresh()

    def _type(self, ch):
        if len(self.scratch) < COLS - 1:
            self.scratch += ch
        self.refresh()

    def _clr(self):
        if self.scratch:
            self.scratch = self.scratch[:-1]
        self.refresh()

    def _scroll(self, d):
        if self.page == "MSGLOG":
            self.msg_offset = max(0, min(max(0, len(self.msgs) - 5),
                                         self.msg_offset + d * 5))
        elif self.page == "MSGDET":
            self.det_offset = max(0, self.det_offset + d * 4)
        self.refresh()

    def _lsk_press(self, side, n):
        fn = self._lsk.get((side, n))
        if fn:
            fn()

    def keyPressEvent(self, ev):
        k = ev.key()
        txt = ev.text().upper()
        mods = ev.modifiers()
        if k == Qt.Key.Key_Backspace:
            self._clr()
        elif k == Qt.Key.Key_Up:
            self._scroll(-1)
        elif k == Qt.Key.Key_Down:
            self._scroll(1)
        elif k == Qt.Key.Key_Escape:
            self.goto("INDEX")
        elif k == Qt.Key.Key_Return or k == Qt.Key.Key_Enter:
            if self.page == "MSGLOG":
                self._apply_filter()
            elif self.page == "SEND":
                self._queue_send()
        elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F6.value:
            n = k - Qt.Key.Key_F1.value
            side = "R" if mods & Qt.KeyboardModifier.ShiftModifier else "L"
            self._lsk_press(side, n)
        elif txt and (txt.isalnum() or txt in " /+-."):
            self._type(txt)
        else:
            super().keyPressEvent(ev)

    # ---- render ----------------------------------------------------------
    def refresh(self):
        self._lsk = {}
        builder = getattr(self, f"_p_{self.page.lower()}", self._p_index)
        title, rows = builder()
        out = [[(center(title), W, False)]]
        out += rows[:12]
        while len(out) < 13:
            out.append([])
        scr = self.scratch or ""
        out.append([(pad(scr if scr else "", "ACARS" if self.ann["MSG"] else ""),
                     A if scr else (G if self.ann["MSG"] else GY), False)])
        self.disp.set_rows(out)

        for i, b in enumerate(self.left_keys):
            on = ("L", i) in self._lsk
            b.setText("←" if on else "·")
            b.setEnabled(True)
        for i, b in enumerate(self.right_keys):
            on = ("R", i) in self._lsk
            b.setText("→" if on else "·")
        self.ind.setText(self.page + ("   ● MSG" if self.ann["MSG"] else ""))
        self.ind.setStyleSheet(f"color:{G if self.ann['MSG'] else GY};")

    def _lbl(self, left="", right="", color=GY):
        """Devuelve UNA fila (lista de filas, para concatenar con +=)."""
        return [[(pad(left, right), color, True)]]

    def _row(self, left="", right="", lcol=G, rcol=None):
        if right:
            txt = pad(left, right)
            return [[(txt[:len(txt) - len(str(right))], lcol, False),
                     (str(right), rcol or lcol, False)]]
        return [[(pad(left), lcol, False)]]

    # ---- páginas ---------------------------------------------------------
    def _p_index(self):
        tail = (self.live.get("r") or "----")
        cs = (self.live.get("flight") or "").strip() or "--------"
        rows = []
        rows += self._lbl("MESSAGES", "TARGET")
        rows += self._row(f"<MSG LOG {len(self.msgs):03d}", f"{cs}>", C, A)
        self._lsk[("L", 0)] = lambda: self.goto("MSGLOG")
        self._lsk[("R", 0)] = lambda: self.goto("FLTDATA")
        rows += self._lbl("LIVE DATA", "AIRCRAFT")
        rows += self._row("<FLT DATA", f"{tail}>", C, A)
        self._lsk[("L", 1)] = lambda: self.goto("FLTDATA")
        self._lsk[("R", 1)] = lambda: self.goto("ACDATA")
        rows += self._lbl("RECEIVER", "DATABASE")
        rows += self._row("<RADIO", "A/C DATA>", C, C)
        self._lsk[("L", 2)] = lambda: self.goto("RADIO")
        self._lsk[("R", 2)] = lambda: self.goto("ACDATA")
        rows += self._lbl("REPORTS", "SYSTEM")
        rows += self._row("<ATC RPT", "STATUS>", C, C)
        self._lsk[("L", 3)] = lambda: self.goto("ATC")
        self._lsk[("R", 3)] = lambda: self.goto("STATUS")
        rows += self._lbl("DOWNLINK (SIM)", "")
        rows += self._row("<SEND MSG", "", C)
        self._lsk[("L", 4)] = lambda: self.goto("SEND")
        rows += self._lbl("", "")
        last = self.msgs[0] if self.msgs else None
        if last:
            rows += self._row(f"LAST {time.strftime('%H:%M:%S', time.localtime(last['ts']))}",
                              f"{last['label']} {last['tail'] or '----'}", GY, W)
        else:
            rows += self._row("AWAITING UPLINK...", "", GY)
        return "ACARS INDEX", rows

    def _p_msglog(self):
        rows = []
        page = self.msgs[self.msg_offset:self.msg_offset + 5]
        for i, m in enumerate(page):
            t = time.strftime("%H:%M:%S", time.localtime(m["ts"] or 0))
            tail = (m["tail"] or "----")[:7]
            flt = (m["flight"] or "")[:7]
            freq = f"{m['freq']:.3f}" if m["freq"] is not None else "---.---"
            rows += self._lbl(f"{t}  {m['mode']}{m['label']}  {freq}",
                              f"ERR{m['err'] or 0} {m['level']:.0f}dB"
                              if m["level"] is not None else "")
            preview = (m["text"] or "").replace("\n", " ").strip()[:8] or "·empty"
            rows += self._row(f"<{tail:<7} {flt:<6}", preview, G, W)
            self._lsk[("L", i)] = (lambda mm=m: self._open_msg(mm))
        for _ in range(5 - len(page)):
            rows += self._lbl("", "")
            rows += self._row("", "")
        rows += self._lbl(f"{self.msg_offset+1}-{self.msg_offset+len(page)}"
                          f" OF {len(self.msgs)}", "FILTER")
        rows += self._row("<INDEX", (self.scratch or "ALL") + ">", C, A)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        self._lsk[("R", 5)] = self._apply_filter
        return "RECEIVED MSGS", rows

    def _apply_filter(self):
        f = self.scratch.strip().upper()
        self.scratch = ""
        rows = self.store.recent(400, tail=f or None)
        self.msgs = rows
        self.msg_offset = 0
        self.refresh()

    def _open_msg(self, m):
        self.sel_msg = m
        self.det_offset = 0
        self.page = "MSGDET"
        self.ann["MSG"] = False
        self.refresh()

    def _p_msgdet(self):
        m = self.sel_msg
        if not m:
            return "MSG DISPLAY", self._row("NO MESSAGE SELECTED", "", A)
        rows = []
        rows += self._lbl(
            time.strftime("%d%b %H:%M:%SZ", time.gmtime(m["ts"] or 0)).upper(),
            f"{m['freq']:.3f}" if m["freq"] is not None else "---.---")
        rows += self._row(f"{(m['tail'] or '----')}", f"{m['flight'] or ''}", A, C)
        rows += self._lbl(f"LBL {m['mode']}/{m['label']}  BLK {m['block_id']}",
                          f"MSN {m['msgno']}  ACK {m['ack'] or 'NAK'}")
        body = wrap(m["text"] or "(mensaje sin texto)")
        shown = body[self.det_offset:self.det_offset + 7]
        for ln in shown:
            rows += [[(ln[:COLS], G, False)]]
        for _ in range(7 - len(shown)):
            rows += [[]]
        rows += self._lbl(f"LINE {self.det_offset+1}/{len(body)}", "TRACK")
        tail = m["tail"] or ""
        rows += self._row("<MSG LOG", (f"{tail}>" if tail else "NO TAIL"), C, A)
        self._lsk[("L", 5)] = lambda: self.goto("MSGLOG")
        if tail:
            self._lsk[("R", 5)] = lambda: self.track_request.emit(
                tail, (m["flight"] or "").strip())
        return "MSG DISPLAY", rows

    def _p_fltdata(self):
        s = self.live
        if not s:
            return "FLIGHT DATA", (self._lbl("", "") +
                                  self._row("NO TARGET SELECTED", "", A) +
                                  self._lbl("", "") +
                                  self._row("<INDEX", "", C))
        def n(k, f="{:.0f}", d="---"):
            v = s.get(k)
            if v is None:
                return d
            try:
                return f.format(v)
            except (ValueError, TypeError):
                return str(v)
        rows = []
        rows += self._lbl("CALLSIGN", "MODE S")
        rows += self._row((s.get("flight") or "").strip() or "--------",
                          (s.get("hex") or "------").upper(), A, W)
        rows += self._lbl("GS / IAS / TAS", "MACH")
        rows += self._row(f"{n('gs')}/{n('ias')}/{n('tas')}", n("mach", "{:.3f}"), G, C)
        rows += self._lbl("ALT BARO / GEOM", "V/S")
        rows += self._row(f"{n('alt_baro')}/{n('alt_geom')}", n("baro_rate", "{:+.0f}"),
                          G, A)
        rows += self._lbl("TRK / HDG MAG", "ROLL")
        rows += self._row(f"{n('track','{:.1f}')}/{n('mag_heading','{:.1f}')}",
                          n("roll", "{:+.1f}"), G, A)
        rows += self._lbl("WIND / OAT / TAT", "SQWK")
        wind = (f"{int(s['wd']):03d}/{int(s['ws'])}"
                if s.get("wd") is not None and s.get("ws") is not None else "---/--")
        rows += self._row(f"{wind} {n('oat')}/{n('tat')}C", s.get("squawk") or "----",
                          G, A)
        rows += self._lbl("SEL ALT/HDG/QNH", "POS AGE")
        rows += self._row(f"{n('nav_altitude_mcp')}/{n('nav_heading','{:.0f}')}/"
                          f"{n('nav_qnh','{:.0f}')}", n("seen_pos", "{:.0f}s"), M, GY)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        self._lsk[("R", 5)] = lambda: self.goto("ACDATA")
        return "FLIGHT DATA", rows

    def _p_acdata(self):
        i, rt = self.acinfo, self.route
        rows = []
        rows += self._lbl("REGISTRATION", "ICAO TYPE")
        rows += self._row(i.get("registration") or (self.live.get("r") or "------"),
                          i.get("icao_type") or (self.live.get("t") or "----"), A, C)
        rows += self._lbl("TYPE", "")
        rows += self._row((i.get("manufacturer", "") + " " +
                           i.get("type", "")).strip()[:COLS] or "---", "", W)
        rows += self._lbl("OPERATOR", "COUNTRY")
        rows += self._row((i.get("registered_owner") or "---")[:17],
                          i.get("registered_owner_country_iso_name") or "--", G, W)
        if rt:
            o = rt.get("origin") or {}
            d = rt.get("destination") or {}
            rows += self._lbl("ROUTE", "AIRLINE")
            rows += self._row(f"{o.get('iata_code','---')} > {d.get('iata_code','---')}",
                              (rt.get("airline") or {}).get("iata", "--"), C, W)
            rows += self._lbl("FROM", "")
            rows += self._row((o.get("municipality") or o.get("name") or "---")[:COLS],
                              "", W)
            rows += self._lbl("TO", "")
            rows += self._row((d.get("municipality") or d.get("name") or "---")[:COLS],
                              "", W)
        else:
            rows += self._lbl("ROUTE", "")
            rows += self._row("NO ROUTE DATA", "", GY)
            rows += self._lbl("MODE S HEX", "")
            rows += self._row((i.get("mode_s") or self.live.get("hex") or "---").upper(),
                              "", W)
            rows += self._lbl("", "")
            rows += self._row("", "")
        rows += self._lbl("", "DATA SRC")
        rows += self._row("<INDEX", "ADSBDB>", C, GY)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        return "AIRCRAFT DATA", rows

    def _p_radio(self):
        s = self.sysinfo
        freqs = s.get("freqs") or []
        counts = s.get("chan_counts") or {}
        rows = []
        rows += self._lbl(f"SOURCE {s.get('mode','OFF')}", "MSGS")
        for idx, f in enumerate(freqs[:5]):
            rows += self._row(f"{idx}  {float(f):.3f} MHz", f"{counts.get(idx,0):04d}",
                              G, C)
            if idx < 4:
                rows += self._lbl("", "")
        while len(rows) < 11:
            rows += self._lbl("", "")
        rows = rows[:11]
        extra = f"+{len(freqs)-5}CH " if len(freqs) > 5 else ""
        gain = s.get("gain", -10)
        gtxt = "AGC" if gain is None or float(gain) < 0 else f"{float(gain):.0f}dB"
        rows += self._row("<INDEX", f"{extra}GAIN {gtxt}", C, GY)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        return "VHF / RECEIVER", rows

    def _p_status(self):
        s = self.sysinfo
        rows = []
        rows += self._lbl(f"SOURCE {s.get('detail','')}"[:18], "LINK")
        rows += self._row(s.get("mode", "OFF"),
                          "ONLINE" if s.get("online") else "OFFLINE",
                          G, G if s.get("online") else A)
        rows += self._lbl("MSGS TOTAL/SESSION", "RATE")
        rows += self._row(f"{s.get('total',0)} / {s.get('session',0)}",
                          f"{s.get('rate',0):.1f}/min", G, C)
        rows += self._lbl("TRAFFIC / ACARS A/C", "API")
        rows += self._row(f"{s.get('traffic',0)} / {s.get('heard',0)}",
                          s.get("api", "---"), G, C)
        rows += self._lbl("STATION", "")
        rows += self._row(s.get("station", "---"), "", W)
        rows += self._lbl("LAST EVENT", "")
        for ln in wrap(s.get("last_status", "-"))[:2]:
            rows += [[(ln[:COLS], GY, False)]]
        while len(rows) < 11:
            rows += [[]]
        rows = rows[:11]
        rows += self._row("<INDEX", "UTC " + time.strftime("%H:%M:%S", time.gmtime()),
                          C, GY)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        return "ACARS STATUS", rows

    def _p_send(self):
        rows = []
        rows += self._lbl("DOWNLINK TEXT (SIM)", "")
        rows += self._row(self.scratch[:COLS] or "____________________", "", A)
        rows += self._lbl("RX ONLY - NO TX", "")
        rows += self._row("RTL-SDR IS RECEIVE", "", GY)
        rows += self._lbl("", "")
        rows += self._row("ONLY. MSG IS LOGGED", "", GY)
        rows += self._lbl("QUEUE", "")
        for s in self.sent[:3]:
            rows += [[(s[:COLS], G, False)]]
        while len(rows) < 11:
            rows += [[]]
        rows = rows[:11]
        rows += self._row("<INDEX", "SEND*", C, A)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        self._lsk[("R", 5)] = self._queue_send
        return "ACARS DOWNLINK", rows

    def _queue_send(self):
        if self.scratch.strip():
            self.sent.insert(0, time.strftime("%H:%M ") + self.scratch.strip())
            self.scratch = ""
        self.refresh()

    def _p_atc(self):
        s = self.live
        rows = []
        rows += self._lbl("POSITION REPORT", "")
        if s.get("lat") is not None:
            lat, lon = s["lat"], s["lon"]
            rows += self._row(f"{abs(lat):06.3f}{'N' if lat>=0 else 'S'} "
                              f"{abs(lon):07.3f}{'E' if lon>=0 else 'W'}", "", G)
            rows += self._lbl("FL / GS / TRK", "UTC")
            alt = s.get("alt_baro")
            fl = f"FL{int(alt)//100:03d}" if isinstance(alt, (int, float)) else "GND"
            rows += self._row(f"{fl} {int(s.get('gs') or 0)}KT "
                              f"{int(s.get('track') or 0):03d}",
                              time.strftime("%H%MZ", time.gmtime()), G, C)
            rows += self._lbl("TEMP / WIND", "")
            wind = (f"{int(s['wd']):03d}/{int(s['ws'])}KT"
                    if s.get("wd") is not None else "---")
            rows += self._row(f"{s.get('oat','--')}C  {wind}", "", W)
            rows += self._lbl("SQUAWK / EMERG", "")
            em = (s.get("emergency") or "none").upper()
            rows += self._row(f"{s.get('squawk','----')}  {em}", "",
                              A if em not in ("NONE", "") else G)
        else:
            rows += self._row("NO POSITION DATA", "", A)
        while len(rows) < 11:
            rows += [[]]
        rows = rows[:11]
        rows += self._row("<INDEX", "", C)
        self._lsk[("L", 5)] = lambda: self.goto("INDEX")
        return "ATC REPORT", rows
