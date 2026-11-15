#!/usr/bin/env python3
"""Inyector de mensajes ACARS de prueba por UDP (mismo formato que acarsdec -j)."""

import argparse
import json
import random
import socket
import time

SAMPLES = [
    ("LV-KKD", "AR1687", "2", "H1", "#DFB(POS-01)/LAT N34.5/LON W58.2/ALT 350"),
    ("LV-FVH", "AR1300", "2", "_d", ""),
    ("LV-GVC", "AR1420", "2", "5Z", "/OUT 1245 /OFF 1302 /ON 1455 /IN 1502"),
    ("PR-GUH", "G31234", "2", "B6", "POS02N2345W04512,FL370,M078,OAT-54"),
    ("N279AT", "AA998", "2", "H1", "#M1BREQWXFOR KJFK/KBOS"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--count", type=int, default=0, help="0 = infinito")
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    n = 0
    while a.count == 0 or n < a.count:
        tail, flight, mode, label, text = random.choice(SAMPLES)
        msg = {
            "timestamp": time.time(),
            "station_id": "SIM",
            "channel": random.randint(0, 4),
            "freq": random.choice([130.025, 130.450, 131.550, 131.725, 131.850]),
            "level": round(random.uniform(-30, -8), 1),
            "error": random.choice([0, 0, 0, 1]),
            "mode": mode,
            "label": label,
            "block_id": str(random.randint(1, 9)),
            "ack": random.choice(["!", ""]),
            "tail": "." + tail,
            "msgno": f"M{random.randint(10,99)}A",
            "flight": flight,
            "text": text,
        }
        s.sendto(json.dumps(msg).encode(), (a.host, a.port))
        n += 1
        print("sent", tail, label)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
