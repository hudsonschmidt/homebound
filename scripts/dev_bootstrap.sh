#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -e "backend[dev]"
echo "Done. Activate with: source .venv/bin/activate"
