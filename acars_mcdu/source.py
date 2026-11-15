"""Fuentes de mensajes ACARS: RTL-SDR local, red (UDP JSON), comando externo o
simulador. Todas entregan el mismo dict con el formato JSON de acarsdec."""

import json
import random
import shlex
import time

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtNetwork import QHostAddress, QUdpSocket

_dec = json.JSONDecoder()

SHELL_CHARS = set("|&;<>()$`\\\"'*?[#~=%")

SIM_SAMPLES = [
    ("LV-KKD", "AR1687", "2", "H1", "#DFB(POS-01)/LAT S34.5/LON W58.2/ALT 350"),
    ("LV-FVH", "AR1300", "2", "_d", ""),
    ("LV-GVC", "AR1420", "2", "5Z", "/OUT 1245 /OFF 1302 /ON 1455 /IN 1502"),
    ("PR-GUH", "G31234", "2", "B6", "POS02N2345W04512,FL370,M078,OAT-54"),
    ("N279AT", "AA998", "2", "H1", "#M1BREQWXFOR KJFK/KBOS"),
]

MODES = {
    "rtl": "RTL-SDR",
    "udp": "UDP",
    "cmd": "CMD",
    "sim": "SIM",
}


def _parse_stream(buf):
    """Extrae objetos JSON completos de un buffer, devuelve (objs, resto)."""
    objs, i = [], 0
    while i < len(buf):
        while i < len(buf) and buf[i] in " \r\n\t":
            i += 1
        if i >= len(buf):
            break
        try:
            obj, end = _dec.raw_decode(buf, i)
        except ValueError:
            break
        objs.append(obj)
        i = end
    return objs, buf[i:]


def acarsdec_args(a, json_stdout=True, udp=None):
    """Arma la lista de argumentos de acarsdec a partir de la config."""
    args = ["-e", "-i", str(a.get("station_id") or "MCDU")]
    args += ["-o", "4"] if json_stdout else ["-o", "0"]
    if udp:
        args += ["-j", udp]
    if a.get("gain") is not None:
        args += ["-g", str(a["gain"])]
    if a.get("ppm"):
        args += ["-p", str(a["ppm"])]
    if a.get("mult"):
        args += ["-m", str(a["mult"])]
    args += ["-r", str(a.get("device", "0"))]
    args += [f"{float(f):.3f}" for f in a["freqs"]]
    return args


class AcarsSource(QObject):
    message = pyqtSignal(dict)
    status = pyqtSignal(str)
    mode_changed = pyqtSignal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.sock = None
        self.proc = None
        self.sim = None
        self._buf = ""
        self.mode = "OFF"
        self.detail = ""
        self.cmdline = ""

    # ---- control ---------------------------------------------------------
    def start(self, mode=None):
        """Arranca la fuente indicada (o la de la config) tras parar la actual."""
        self.stop()
        mode = mode or self.cfg.get("source", {}).get("mode", "udp")
        try:
            if mode == "rtl":
                self.start_process()
            elif mode == "cmd":
                self.start_command(self.cfg["source"].get("command", ""))
            elif mode == "sim":
                self.start_sim()
            else:
                self.start_udp()
        except Exception as exc:
            self.mode = "ERROR"
            self.status.emit(f"no se pudo iniciar la fuente: {exc}")
        self.mode_changed.emit(self.mode)

    def stop(self):
        if self.proc is not None:
            proc, self.proc = self.proc, None
            try:
                proc.readyReadStandardOutput.disconnect()
                proc.readyReadStandardError.disconnect()
                proc.finished.disconnect()
                proc.errorOccurred.disconnect()
            except TypeError:
                pass
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.terminate()
                if not proc.waitForFinished(2000):
                    proc.kill()
                    proc.waitForFinished(1000)
            proc.deleteLater()
        if self.sock is not None:
            self.sock.close()
            self.sock.deleteLater()
            self.sock = None
        if self.sim is not None:
            self.sim.stop()
            self.sim = None
        self._buf = ""
        self.mode = "OFF"
        self.detail = ""

    # ---- red -------------------------------------------------------------
    def start_udp(self):
        u = self.cfg["udp"]
        self.sock = QUdpSocket(self)
        ok = self.sock.bind(
            QHostAddress(u.get("host") or "0.0.0.0"), int(u["port"]),
            QUdpSocket.BindFlag.ShareAddress |
            QUdpSocket.BindFlag.ReuseAddressHint)
        self.sock.readyRead.connect(self._on_udp)
        self.mode = "UDP" if ok else "ERROR"
        self.detail = f"{u.get('host','0.0.0.0')}:{u['port']}"
        self.status.emit(f"UDP {self.detail} {'escuchando' if ok else 'BIND FAIL'}")

    def _on_udp(self):
        while self.sock and self.sock.hasPendingDatagrams():
            dg = self.sock.receiveDatagram()
            try:
                txt = bytes(dg.data()).decode("utf-8", "replace")
                objs, _ = _parse_stream(txt)
                for o in objs:
                    self.message.emit(o)
            except Exception as exc:
                self.status.emit(f"UDP parse err: {exc}")

    # ---- RTL-SDR local ---------------------------------------------------
    def start_process(self):
        a = self.cfg["acarsdec"]
        args = acarsdec_args(a)
        self._spawn(a.get("bin", "acarsdec"), args)
        self.mode = "RTL-SDR"
        dev = a.get("device", "0")
        self.detail = f"dev {dev} · {len(a['freqs'])} canales"

    # ---- comando externo -------------------------------------------------
    def start_command(self, cmd):
        cmd = (cmd or "").strip()
        if not cmd:
            raise ValueError("comando vacío")
        if set(cmd) & SHELL_CHARS:
            self._spawn("/bin/bash", ["-lc", cmd])
        else:
            parts = shlex.split(cmd)
            self._spawn(parts[0], parts[1:])
        self.mode = "CMD"
        self.detail = cmd[:60]

    def _spawn(self, prog, args):
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.errorOccurred.connect(
            lambda e: self.status.emit(f"error de proceso: {e.name}"))
        self.proc.finished.connect(
            lambda c, s: self.status.emit(f"{prog} terminó (rc={c})"))
        self.cmdline = prog + " " + shlex.join(args)
        self.proc.start(prog, args)
        self.status.emit(self.cmdline)

    def _on_stdout(self):
        if self.proc is None:
            return
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        objs, self._buf = _parse_stream(self._buf)
        for o in objs:
            self.message.emit(o)
        if len(self._buf) > 65536:
            self._buf = ""

    def _on_stderr(self):
        if self.proc is None:
            return
        txt = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        for line in txt.splitlines():
            if line.strip():
                self.status.emit(line.strip())

    # ---- simulador -------------------------------------------------------
    def start_sim(self):
        self.sim = QTimer(self)
        self.sim.setInterval(int(self.cfg.get("source", {}).get("sim_interval", 4)) * 1000)
        self.sim.timeout.connect(self._sim_tick)
        self.sim.start()
        self.mode = "SIM"
        self.detail = "mensajes de prueba"
        self.status.emit("simulador activo (sin radio)")
        QTimer.singleShot(600, self._sim_tick)

    def _sim_tick(self):
        tail, flight, mode, label, text = random.choice(SIM_SAMPLES)
        self.message.emit({
            "timestamp": time.time(), "station_id": "SIM",
            "channel": random.randint(0, 4),
            "freq": random.choice(self.cfg["acarsdec"]["freqs"]),
            "level": round(random.uniform(-30, -8), 1),
            "error": random.choice([0, 0, 0, 1]), "mode": mode, "label": label,
            "block_id": str(random.randint(1, 9)),
            "ack": random.choice(["!", ""]), "tail": "." + tail,
            "msgno": f"M{random.randint(10, 99)}A", "flight": flight, "text": text,
        })
