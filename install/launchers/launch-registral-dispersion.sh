#!/bin/bash
cd "$(dirname "$0")"
if [ ! -f ".venv/bin/activate" ]; then
  echo ""
  echo "Virtual environment not found."
  echo "Run install/linux/install.sh once to set up this folder."
  echo ""
  read -r -p "Press Enter to close..."
  exit 1
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"
python -m registral_dispersion
