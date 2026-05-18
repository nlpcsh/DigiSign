#!/usr/bin/env bash
set -e

# Requires Python 3.10 or later
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

# ===== CONFIG =====
APP_NAME="Digital PDF Signer"
APP_DIR="$REPO_ROOT"
PYTHON_FILE="$REPO_ROOT/main.py"
ICON_FILE="$APP_DIR/icon.png"
DESKTOP_FILE="$HOME/.local/share/applications/digisign.desktop"
RUN_SCRIPT="$REPO_ROOT/run.sh"

# ===== CREATE APP DIRECTORY =====
mkdir -p "$APP_DIR"

# ===== CREATE RUN SCRIPT =====
cat > "$RUN_SCRIPT" <<EOF
#!/bin/bash

# Activate virtual environment if it exists
if [ -d "$APP_DIR/.venv" ]; then
    source "$APP_DIR/.venv/bin/activate"
fi

python3 "$PYTHON_FILE"
EOF

chmod +x "$RUN_SCRIPT"

# ===== CREATE DESKTOP SHORTCUT =====
mkdir -p "$HOME/.local/share/applications"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Python Application
Exec=$RUN_SCRIPT
Icon=$ICON_FILE
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE"

# ===== OPTIONAL DESKTOP ICON =====
cp "$DESKTOP_FILE" "$HOME/Desktop/digisign.desktop" 2>/dev/null
chmod +x "$HOME/Desktop/digisign.desktop" 2>/dev/null

echo "Installation complete."
echo "Launcher created:"
echo " - Applications menu"
echo " - Desktop shortcut"