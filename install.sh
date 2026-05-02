#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -d "$REPO_ROOT/.venv" ]; then
  echo "Virtual environment already exists at $REPO_ROOT/.venv"
else
  python3 -m venv "$REPO_ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$REPO_ROOT/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REPO_ROOT/requirements.txt"

echo "DigiSign dependencies installed in $REPO_ROOT/.venv"
echo "Activate the environment with: source $REPO_ROOT/.venv/bin/activate"
echo "Run the app with: python $REPO_ROOT/main.py"