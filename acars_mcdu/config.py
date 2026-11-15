import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/acars_mcdu")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR = os.path.expanduser("~/.cache/acars_mcdu")
TILE_DIR = os.path.join(CACHE_DIR, "tiles")
DB_PATH = os.path.join(CACHE_DIR, "acars.db")

USER_AGENT = "acars-mcdu/1.0"

DEFAULTS = {
    "station": {"name": "HOME", "lat": -34.6037, "lon": -58.3816},
    "acarsdec": {
        "bin": "acarsdec",
        "device": "0",
        "gain": 40,   # fija suele rendir mejor que AGC (-10) en ACARS
        "ppm": 0,
        "mult": 160,
        "freqs": [130.025, 130.450, 131.550, 131.725, 131.850],
        "station_id": "ACARS-MCDU",
    },
    "udp": {"host": "0.0.0.0", "port": 5555},
    # mode: rtl (dongle local) | udp (red) | cmd (proceso externo) | sim
    "source": {"mode": "udp", "command": "", "sim_interval": 4},
    "map": {
        "zoom": 6,
        # Esri Dark Gray Canvas (sin API key). Ojo: el orden es /{z}/{y}/{x}
        "tiles": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/"
                 "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "overlay": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/"
                   "World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        "range_rings_nm": [100, 200, 300],
    },
    "poll": {"traffic_sec": 12, "target_sec": 5, "radius_nm": 250},
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(TILE_DIR, exist_ok=True)
    cfg = DEFAULTS
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as fh:
                stored = json.load(fh)
            cfg = _merge(DEFAULTS, stored)
            if stored != cfg:  # completar claves nuevas en disco
                save(cfg)
        except Exception:
            pass
    else:
        save(cfg)
    return cfg


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as fh:
        json.dump(cfg, fh, indent=2)
