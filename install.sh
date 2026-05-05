#!/usr/bin/env bash
set -e

# Requires Python 3.8 or later
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_CMD=python3
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  PYTHON_CMD=python
fi

if [ -d "$REPO_ROOT/.venv" ]; then
  echo "Virtual environment already exists at $REPO_ROOT/.venv"
else
  "$PYTHON_CMD" -m venv "$REPO_ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$REPO_ROOT/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REPO_ROOT/requirements.txt"

echo "DigiSign dependencies installed in $REPO_ROOT/.venv"
echo "Activate the environment with: source $REPO_ROOT/.venv/bin/activate"
echo "Run the app with: python $REPO_ROOT/main.py"