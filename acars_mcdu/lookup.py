"""Clientes HTTP asíncronos: adsb.lol (estado en vivo) y adsbdb (matrícula/ruta)."""

import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from . import config

ADSB = "https://api.adsb.lol/v2"
ADSBDB = "https://api.adsbdb.com/v0"


class AdsbClient(QObject):
    traffic = pyqtSignal(list)          # tráfico alrededor de la estación
    target = pyqtSignal(dict)           # estado en vivo del avión seleccionado
    ac_info = pyqtSignal(str, dict)     # matrícula -> ficha estática
    route_info = pyqtSignal(str, dict)  # callsign -> ruta
    photo = pyqtSignal(str, bytes)      # matrícula -> jpg
    error = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.nam = QNetworkAccessManager(self)
        self._inflight = set()

    def _get(self, url, kind, key=None):
        tag = (kind, url)
        if tag in self._inflight:
            return
        self._inflight.add(tag)
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", config.USER_AGENT.encode())
        req.setRawHeader(b"Accept", b"application/json")
        req.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        rep = self.nam.get(req)
        rep.finished.connect(lambda: self._done(rep, tag, kind, key))

    def _done(self, rep, tag, kind, key):
        try:
            self._inflight.discard(tag)
            raw = bytes(rep.readAll())
            err = rep.error().value
            rep.deleteLater()
        except RuntimeError:
            return   # la app se está cerrando

        if err:
            self.error.emit(f"{kind}: net err {err}")
            return
        if kind == "photo":
            self.photo.emit(key, raw)
            return
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:
            self.error.emit(f"{kind}: {exc}")
            return

        if kind == "traffic":
            self.traffic.emit(data.get("ac") or [])
        elif kind == "target":
            ac = data.get("ac") or []
            if ac:
                self.target.emit(ac[0])
        elif kind == "aircraft":
            info = (data.get("response") or {}).get("aircraft")
            if isinstance(info, dict):
                self.store.cache_put("ac_cache", key, info)
                self.ac_info.emit(key, info)
                thumb = info.get("url_photo_thumbnail") or info.get("url_photo")
                if thumb:
                    self._get(thumb, "photo", key)
        elif kind == "route":
            rt = (data.get("response") or {}).get("flightroute")
            if isinstance(rt, dict):
                self.store.cache_put("route_cache", key, rt)
                self.route_info.emit(key, rt)

    # ---- API pública -----------------------------------------------------
    def poll_traffic(self, lat, lon, radius_nm):
        self._get(f"{ADSB}/point/{lat:.4f}/{lon:.4f}/{int(radius_nm)}", "traffic")

    def track(self, hexid=None, reg=None, callsign=None):
        if hexid:
            self._get(f"{ADSB}/hex/{hexid.lower()}", "target")
        elif reg:
            self._get(f"{ADSB}/registration/{reg.upper()}", "target")
        elif callsign:
            self._get(f"{ADSB}/callsign/{callsign.upper()}", "target")

    def fetch_aircraft(self, reg):
        reg = (reg or "").upper().strip()
        if not reg:
            return
        cached = self.store.cache_get("ac_cache", reg)
        if cached:
            self.ac_info.emit(reg, cached)
            return
        self._get(f"{ADSBDB}/aircraft/{reg}", "aircraft", reg)

    def fetch_route(self, callsign):
        cs = (callsign or "").upper().strip()
        if not cs:
            return
        cached = self.store.cache_get("route_cache", cs)
        if cached:
            self.route_info.emit(cs, cached)
            return
        self._get(f"{ADSBDB}/callsign/{cs}", "route", cs)
