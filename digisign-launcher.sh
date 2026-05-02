#!/usr/bin/env bash
# DigiSign Launcher Script
# This script activates the virtual environment and launches DigiSign

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
    source "$REPO_ROOT/.venv/bin/activate"
fi

cd "$REPO_ROOT"
python main.py