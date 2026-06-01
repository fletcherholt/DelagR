#!/usr/bin/env bash
# Build DelagR as a single macOS binary (dist/DelagR-macos).
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Generate a .icns from icon.png for the bundled icon.
ICONSET="build/DelagR.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for size in 16 32 64 128 256 512; do
  sips -z "$size" "$size" icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" icon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/DelagR.icns

pyinstaller \
  --noconfirm --clean --onefile \
  --name DelagR-macos \
  --icon build/DelagR.icns \
  --collect-all webview \
  src/delagr.py

echo "Built: $(pwd)/dist/DelagR-macos"
