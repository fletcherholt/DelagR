#!/usr/bin/env bash
# Build DelagR as a single Linux binary (dist/DelagR-linux).
# Uses the Qt (QtWebEngine) backend so the renderer is pip-installable and
# bundles cleanly, rather than depending on system GTK/WebKit.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

pyinstaller \
  --noconfirm --clean --onefile \
  --name DelagR-linux \
  --collect-all webview \
  --collect-all PyQt5 \
  src/delagr.py

echo "Built: $(pwd)/dist/DelagR-linux"
