#!/bin/bash
# Activate the Homebound virtual environment
source "$(dirname "$0")/.venv/bin/activate"
echo "Activated virtual environment at $(dirname "$0")/.venv"
echo "Python: $(which python)"
echo "pytest: $(pytest --version 2>/dev/null || echo 'not found')"
