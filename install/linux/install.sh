#!/bin/bash
# Registral_Dispersion - One-click installer (Linux)
# Run: chmod +x install/linux/install.sh && ./install/linux/install.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo ""
echo "============================================================"
echo "  Registral_Dispersion - One-click installer (Linux)"
echo "============================================================"
echo ""
echo "Copyright (c) 2026 Luis Raimundo. All rights reserved."
echo ""

find_python() {
  for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      if "$cmd" -c 'import sys; assert sys.version_info>=(3,10)' 2>/dev/null; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

ensure_system_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "Checking optional system packages (python3-venv)..."
    if ! dpkg -s python3-venv >/dev/null 2>&1; then
      echo "Installing python3-venv (may ask for sudo password)..."
      sudo apt-get update -qq
      sudo apt-get install -y python3-venv python3-pip
    fi
  fi
}

PY="$(find_python || true)"

if [ -z "$PY" ]; then
  ensure_system_deps
  PY="$(find_python || true)"
fi

if [ -z "$PY" ]; then
  echo ""
  echo "Python 3.10+ not found. Install with your package manager, e.g.:"
  echo "  sudo apt install python3 python3-venv python3-pip   # Debian/Ubuntu"
  echo "  sudo dnf install python3 python3-pip                # Fedora"
  exit 1
fi

echo "Using: $PY ($($PY --version))"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e .

cp "install/launchers/launch-registral-dispersion.sh" "launch-registral-dispersion.sh"
cp "install/launchers/summarize-score.sh" "summarize-score.sh"
chmod +x "launch-registral-dispersion.sh" "summarize-score.sh"

echo ""
echo "============================================================"
echo "  Installation complete."
echo "============================================================"
echo ""
echo "Run: ./launch-registral-dispersion.sh"
echo "Or:  ./summarize-score.sh --score path/to/score.musicxml"
echo ""

read -r -p "Launch the interface now? [Y/n]: " RUN
if [[ ! "$RUN" =~ ^[Nn]$ ]]; then
  ./launch-registral-dispersion.sh
fi
