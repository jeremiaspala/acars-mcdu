#!/usr/bin/env bash
# Construye dist/ACARS_MCDU-<version>-x86_64.AppImage (Python + PyQt6 embebidos).
#
#   ./packaging/build-appimage.sh [version]
#
# Requiere red (baja la AppImage base de Python, las wheels y appimagetool) y
# python3-venv. acarsdec y librtlsdr NO se empaquetan: son del sistema.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
VERSION="${1:-$(grep -m1 '^version' "$ROOT/pyproject.toml" | cut -d'"' -f2)}"
PY="${PYTHON_VERSION:-3.12}"
WORK="$(mktemp -d)"
KEEP="${KEEP_WORK:-0}"
[ "$KEEP" = "1" ] || trap 'rm -rf "$WORK"' EXIT

# Módulos Qt que la app no usa (recortan ~170 MB del AppImage)
QT_DROP=(3DAnimation 3DCore 3DExtras 3DInput 3DLogic 3DQuick 3DQuickAnimation
  3DQuickExtras 3DQuickInput 3DQuickRender 3DQuickScene2D 3DQuickScene3D
  3DRender Bluetooth Charts DataVisualization Designer DesignerComponents
  EglFSDeviceIntegration FFmpegStub Graphs Help Labs Multimedia Nfc Pdf
  Positioning Qml Quick RemoteObjects Scxml Sensors SerialPort SpatialAudio
  Sql StateMachine Test TextToSpeech WebChannel WebEngine WebSockets
  ShaderTools Svg)

echo "==> entorno de build"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" -q install --upgrade pip python-appimage

echo "==> metadata"
APPDIR_SRC="$WORK/app"
mkdir -p "$APPDIR_SRC"
cp "$ROOT/packaging/appimage/acars-mcdu.desktop" "$APPDIR_SRC/acars-mcdu.desktop"
cp "$ROOT/docs/icon.png" "$APPDIR_SRC/acars-mcdu.png"
cat > "$APPDIR_SRC/entrypoint.sh" <<'ENTRY'
#! /bin/bash
{{ python-executable }} -m acars_mcdu "$@"
ENTRY
printf '%s\n' "$ROOT" > "$APPDIR_SRC/requirements.txt"   # instala el paquete local

echo "==> AppDir (python $PY + PyQt6 + acars-mcdu)"
cd "$WORK"
"$WORK/venv/bin/python" -m python_appimage build app --no-packaging -p "$PY" app
APPDIR="$(find "$WORK" -maxdepth 1 -type d -name '*x86_64' | head -1)"
[ -n "$APPDIR" ] || { echo "no se generó el AppDir" >&2; exit 1; }
mv "$APPDIR" "$WORK/AppDir"
APPDIR="$WORK/AppDir"
SP="$(find "$APPDIR/opt" -maxdepth 4 -type d -name site-packages | head -1)"

echo "==> poda ($(du -sh "$APPDIR" | cut -f1) antes)"
rm -rf "$SP"/{pip,setuptools,wheel,build,packaging,certifi,pyproject_hooks,pkg_resources} \
       "$SP"/{pip-*,setuptools-*,wheel-*,build-*,packaging-*,certifi-*,pyproject_hooks-*}.dist-info \
       "$SP"/PyQt6/Qt6/qml "$SP"/PyQt6/Qt6/translations \
       "$SP"/PyQt6/Qt6/plugins/{multimedia,position,sqldrivers,renderers,qmltooling,sceneparsers,geometryloaders,texttospeech,webview,networkinformation/libqglib*} \
       2>/dev/null || true
for mod in "${QT_DROP[@]}"; do
  rm -f "$SP"/PyQt6/Qt"$mod"*.abi3.so \
        "$SP"/PyQt6/Qt6/lib/libQt6"$mod"*.so.6 \
        "$SP"/PyQt6/bindings/Qt"$mod"* 2>/dev/null || true
  rm -rf "$SP"/PyQt6/Qt6/libexec/QtWebEngineProcess 2>/dev/null || true
done
find "$APPDIR" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo "    $(du -sh "$APPDIR" | cut -f1) después"

echo "==> verificando el AppDir"
QT_QPA_PLATFORM=offscreen "$APPDIR/AppRun" --help >/dev/null \
  || { echo "el AppDir no arranca" >&2; exit 1; }

echo "==> appimagetool"
TOOL="$WORK/appimagetool"
curl -sSL -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x "$TOOL"

OUT="$ROOT/dist/ACARS_MCDU-${VERSION}-x86_64.AppImage"
mkdir -p "$ROOT/dist"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT" >/dev/null
chmod +x "$OUT"
echo "==> listo"
ls -lh "$OUT"
