#!/bin/bash
# Registral_Dispersion - One-click installer (macOS)
# Double-click in Finder, or: chmod +x INSTALL.command && ./INSTALL.command

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo ""
echo "============================================================"
echo "  Registral_Dispersion - One-click installer (macOS)"
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

PY="$(find_python || true)"

if [ -z "$PY" ]; then
  echo "Python 3.10+ not found."
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Python via Homebrew..."
    brew install python@3.12
    PY="$(find_python || true)"
  fi
fi

if [ -z "$PY" ]; then
  echo ""
  echo "Please install Python 3.10+ from https://www.python.org/downloads/"
  echo "or run: brew install python@3.12"
  echo "Then run this installer again."
  read -r -p "Press Enter to close..."
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

cp "install/launchers/Launch-Registral-Dispersion.command" "Launch-Registral-Dispersion.command"
cp "install/launchers/summarize-score.sh" "summarize-score.sh"
chmod +x "Launch-Registral-Dispersion.command" "summarize-score.sh"

echo ""
echo "============================================================"
echo "  Installation complete."
echo "============================================================"
echo ""
echo "Double-click: Launch-Registral-Dispersion.command"
echo "Or run: ./summarize-score.sh --score path/to/score.musicxml"
echo ""
read -r -p "Launch the interface now? [Y/n]: " RUN
if [[ ! "$RUN" =~ ^[Nn]$ ]]; then
  open "Launch-Registral-Dispersion.command" 2>/dev/null || ./Launch-Registral-Dispersion.command
fi

read -r -p "Press Enter to close..."
