#!/usr/bin/env bash
# Lanzador de ACARS MCDU.
#
#   ./start.sh            -> última fuente guardada en el config
#   ./start.sh rtl        -> dongle RTL-SDR local (la app lanza acarsdec)
#   ./start.sh udp [port] -> escucha JSON de un acarsdec -j (local o remoto)
#   ./start.sh sim        -> mensajes de prueba, sin radio
#   ./start.sh cmd "ssh pi@sdr 'acarsdec -o 4 -e -r 0 131.550'"
#   ./start.sh split      -> arranca acarsdec -j acá y la GUI en modo UDP
#
# Variables: DEV (dongle), GAIN, PPM, PORT, FREQS, LAT, LON
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

DEV="${DEV:-0}"
GAIN="${GAIN:--10}"
PPM="${PPM:-0}"
PORT="${PORT:-5555}"
FREQS="${FREQS:-130.025 130.450 131.550 131.725 131.850}"

die() { echo "error: $*" >&2; exit 1; }

python3 -c 'import PyQt6.QtWidgets, PyQt6.QtNetwork' 2>/dev/null \
  || die "falta python3-pyqt6 (sudo apt install python3-pyqt6)"

MODE="${1:-}"
[ $# -gt 0 ] && shift || true

need_acarsdec() {
  command -v acarsdec >/dev/null || die "acarsdec no está en el PATH"
  if pgrep -x acarsdec >/dev/null; then
    echo "aviso: ya hay un acarsdec corriendo; el dongle puede estar ocupado" >&2
  fi
}

case "$MODE" in
  "")
    exec python3 -m acars_mcdu "$@"
    ;;
  rtl)
    need_acarsdec
    exec python3 -m acars_mcdu --source rtl --device "$DEV" --gain "$GAIN" \
         --ppm "$PPM" --freqs $FREQS "$@"
    ;;
  udp)
    if [[ "${1:-}" =~ ^[0-9]+$ ]]; then PORT="$1"; shift; fi
    exec python3 -m acars_mcdu --source udp --port "$PORT" "$@"
    ;;
  sim)
    exec python3 -m acars_mcdu --source sim "$@"
    ;;
  cmd)
    [ $# -ge 1 ] || die 'uso: ./start.sh cmd "comando que imprime JSON de acarsdec"'
    CMD="$1"; shift
    exec python3 -m acars_mcdu --source cmd --command "$CMD" "$@"
    ;;
  split)
    need_acarsdec
    acarsdec -o 0 -e -i ACARS-MCDU -g "$GAIN" -p "$PPM" \
             -j 127.0.0.1:"$PORT" -r "$DEV" $FREQS &
    DECPID=$!
    trap 'kill $DECPID 2>/dev/null || true' EXIT INT TERM
    sleep 1
    kill -0 $DECPID 2>/dev/null || die "acarsdec no arrancó (¿dongle ocupado?)"
    python3 -m acars_mcdu --source udp --port "$PORT" "$@"
    ;;
  *)
    die "modo desconocido '$MODE' (rtl|udp|sim|cmd|split)"
    ;;
esac
