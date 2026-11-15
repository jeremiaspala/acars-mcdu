"""Selector de fuente ACARS: RTL-SDR local, red (UDP), comando externo o simulador."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSpinBox, QStackedWidget, QVBoxLayout,
                             QWidget)

from . import rtl
from . import theme as T
from .source import MODES, acarsdec_args

ORDER = ["rtl", "udp", "cmd", "sim"]
TITLES = {
    "rtl": "RTL-SDR local  ·  acarsdec sobre el dongle USB",
    "udp": "Red  ·  recibir JSON de acarsdec por UDP (local o remoto)",
    "cmd": "Comando externo  ·  cualquier proceso que escupa JSON de acarsdec",
    "sim": "Simulador  ·  mensajes de prueba, sin radio",
}

EXTRA_QSS = f"""
QLineEdit, QComboBox, QSpinBox {{
    background: {T.SURFACE_2}; border: 1px solid {T.BORDER};
    border-radius: 8px; padding: 5px 9px; color: {T.TEXT};
    min-height: 22px;
    selection-background-color: {T.CYAN}; selection-color: #06121a;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent; border: 0; width: 16px;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow {{ width: 9px; height: 9px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {T.CYAN}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {T.SURFACE_2}; border: 1px solid {T.BORDER_HI};
    selection-background-color: rgba(34,211,238,0.18); color: {T.TEXT};
}}
QLabel#hint {{ color: {T.MUTED}; font-size: 11px; }}
"""


class SourceDialog(QDialog):
    def __init__(self, cfg, current_mode="udp", parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._ready = False
        self.setWindowTitle("Fuente ACARS")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(T.QSS + EXTRA_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QLabel("FUENTE DE MENSAJES")
        head.setObjectName("cardTitle")
        root.addWidget(head)

        self.mode = QComboBox()
        for m in ORDER:
            self.mode.addItem(f"{MODES[m]}   —   {TITLES[m].split('·')[1].strip()}", m)
        self.mode.setCurrentIndex(
            ORDER.index(cfg.get("source", {}).get("mode", "udp"))
            if cfg.get("source", {}).get("mode", "udp") in ORDER else 1)
        self.mode.currentIndexChanged.connect(self._on_mode)
        root.addWidget(self.mode)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_rtl())
        self.stack.addWidget(self._page_udp())
        self.stack.addWidget(self._page_cmd())
        self.stack.addWidget(self._page_sim())
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 14)
        cl.addWidget(self.stack)
        root.addWidget(card)

        self.preview = QLabel("")
        self.preview.setObjectName("hint")
        self.preview.setFont(T.mono(9))
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)

        bb = QDialogButtonBox()
        self.b_apply = bb.addButton("Conectar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_apply.setObjectName("accent")
        bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self._ready = True
        self._on_mode()

    # ---- páginas ---------------------------------------------------------
    def _page_rtl(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(8)
        a = self.cfg["acarsdec"]
        row = QHBoxLayout()
        self.dev = QComboBox()
        self.dev.setEditable(True)
        b = QPushButton("Detectar")
        b.clicked.connect(self._scan)
        row.addWidget(self.dev, 1)
        row.addWidget(b)
        cont = QWidget()
        cont.setLayout(row)
        f.addRow("Dongle", cont)

        self.freqs = QLineEdit(" ".join(f"{float(x):.3f}" for x in a["freqs"]))
        self.freqs.textChanged.connect(self._preview)
        f.addRow("Frecuencias MHz", self.freqs)

        self.gain = QLineEdit(str(a.get("gain", -10)))
        self.gain.textChanged.connect(self._preview)
        f.addRow("Ganancia dB (-10 = AGC)", self.gain)

        self.ppm = QSpinBox()
        self.ppm.setRange(-200, 200)
        self.ppm.setValue(int(a.get("ppm", 0)))
        self.ppm.valueChanged.connect(self._preview)
        f.addRow("Corrección ppm", self.ppm)

        self.mult = QComboBox()
        for v, lbl in ((160, "160 · 2.0 MS/s"), (192, "192 · 2.4 MS/s")):
            self.mult.addItem(lbl, v)
        self.mult.setCurrentIndex(0 if int(a.get("mult", 160)) == 160 else 1)
        self.mult.currentIndexChanged.connect(self._preview)
        f.addRow("Sample rate", self.mult)

        self.stid = QLineEdit(str(a.get("station_id", "ACARS-MCDU")))
        f.addRow("Station ID", self.stid)

        hint = QLabel("Hasta 16 canales, todos dentro del ancho de muestreo "
                      "(~2 MHz). acarsdec abre el dongle directamente.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        self._scan()
        return w

    def _page_udp(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(8)
        u = self.cfg["udp"]
        self.uhost = QLineEdit(str(u.get("host", "0.0.0.0")))
        self.uhost.textChanged.connect(self._preview)
        f.addRow("Escuchar en", self.uhost)
        self.uport = QSpinBox()
        self.uport.setRange(1, 65535)
        self.uport.setValue(int(u.get("port", 5555)))
        self.uport.valueChanged.connect(self._preview)
        f.addRow("Puerto UDP", self.uport)
        hint = QLabel(
            "Para recibir de otra máquina poné <b>0.0.0.0</b> acá y en el host "
            "remoto corré:<br><code>acarsdec -o 0 -e -j IP_DE_ESTA_PC:PUERTO "
            "-r 0 131.550 131.725</code>")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        return w

    def _page_cmd(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(8)
        self.cmd = QLineEdit(self.cfg.get("source", {}).get("command", ""))
        self.cmd.setPlaceholderText("acarsdec -o 4 -e -r 0 131.550 131.725")
        self.cmd.textChanged.connect(self._preview)
        f.addRow("Comando", self.cmd)
        hint = QLabel(
            "La salida estándar debe ser JSON de acarsdec (<code>-o 4</code>). "
            "Sirve para un receptor remoto por SSH, un dongle en otra PC con "
            "rtl_tcp + acarsdec, o reproducir un log:<br>"
            "<code>ssh pi@sdr 'acarsdec -o 4 -e -r 0 131.550'</code><br>"
            "<code>cat capturas.json</code>")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        return w

    def _page_sim(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(8)
        self.sim_int = QSpinBox()
        self.sim_int.setRange(1, 120)
        self.sim_int.setValue(int(self.cfg.get("source", {}).get("sim_interval", 4)))
        self.sim_int.valueChanged.connect(self._preview)
        f.addRow("Intervalo (s)", self.sim_int)
        hint = QLabel("Genera mensajes ACARS de ejemplo para probar la interfaz "
                      "sin radio. Las matrículas son reales, así que el mapa y "
                      "los datos de vuelo se consultan igual.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        return w

    # ---- lógica ----------------------------------------------------------
    def _scan(self):
        cur = self.dev.currentText()
        self.dev.clear()
        devs = rtl.devices()
        for d in devs:
            self.dev.addItem(d["label"], str(d["index"]))
        if not devs:
            self.dev.addItem("sin dongles detectados", "0")
        want = str(self.cfg["acarsdec"].get("device", "0"))
        for i in range(self.dev.count()):
            if self.dev.itemData(i) == want or self.dev.itemText(i) == cur:
                self.dev.setCurrentIndex(i)
                break
        self._preview()

    def _on_mode(self):
        self.stack.setCurrentIndex(self.mode.currentIndex())
        self._preview()

    def _mode_key(self):
        return self.mode.currentData()

    def _preview(self):
        if not self._ready:
            return
        m = self._mode_key()
        if m == "rtl":
            a = dict(self.cfg["acarsdec"])
            a.update(self._rtl_values())
            txt = "acarsdec " + " ".join(acarsdec_args(a))
        elif m == "udp":
            txt = (f"bind udp://{self.uhost.text()}:{self.uport.value()}   "
                   f"← acarsdec -j …")
        elif m == "cmd":
            txt = self.cmd.text() or "(sin comando)"
        else:
            txt = f"simulador · 1 mensaje cada {self.sim_int.value()} s"
        self.preview.setText("▸ " + txt)

    def _rtl_values(self):
        try:
            gain = float(self.gain.text())
        except ValueError:
            gain = -10
        freqs = []
        for tok in self.freqs.text().replace(",", " ").split():
            try:
                freqs.append(float(tok))
            except ValueError:
                pass
        return {
            "device": self.dev.currentData() or self.dev.currentText().strip(),
            "freqs": freqs or self.cfg["acarsdec"]["freqs"],
            "gain": gain,
            "ppm": self.ppm.value(),
            "mult": self.mult.currentData(),
            "station_id": self.stid.text().strip() or "ACARS-MCDU",
        }

    def result_config(self):
        """Devuelve la config actualizada según lo elegido."""
        cfg = self.cfg
        m = self._mode_key()
        cfg.setdefault("source", {})["mode"] = m
        if m == "rtl":
            cfg["acarsdec"].update(self._rtl_values())
        elif m == "udp":
            cfg["udp"]["host"] = self.uhost.text().strip() or "0.0.0.0"
            cfg["udp"]["port"] = self.uport.value()
        elif m == "cmd":
            cfg["source"]["command"] = self.cmd.text().strip()
        else:
            cfg["source"]["sim_interval"] = self.sim_int.value()
        return cfg
