#!/usr/bin/env bash
# install.sh — Sets up AFFiNE Discord RPC as a systemd user service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_NAME="affine-discord-rpc.service"
CONFIG_FILE="$SCRIPT_DIR/config.yaml"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

echo ""
echo "  AFFiNE Discord RPC — Installer"
echo "  ================================"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────────────────

command -v python3 &>/dev/null || error "python3 not found. Install Python 3.10+ first."

PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
if [[ "$PYTHON_MAJOR" -lt 3 || ( "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ) ]]; then
    error "Python 3.10+ is required (found $(python3 --version))."
fi
info "Python $(python3 --version) — OK"

[[ -f "$CONFIG_FILE" ]] || error "$CONFIG_FILE not found."

if grep -q "REPLACE_WITH" "$CONFIG_FILE"; then
    warn "config.yaml still has placeholder values!"
    warn "Edit $CONFIG_FILE and fill in:"
    warn "  • client_id  — Discord Application ID"
    echo ""
fi

# Optional tools warning (fallback for X11/XWayland setups)
if ! command -v qdbus6 &>/dev/null; then
    warn "qdbus6 not found — KWin window detection will not work."
    warn "On KDE Plasma it should be pre-installed. Check: which qdbus6"
fi
if ! command -v xdotool &>/dev/null && ! command -v wmctrl &>/dev/null; then
    warn "Neither xdotool nor wmctrl found (X11/XWayland fallback only)."
    warn "On KDE Plasma Wayland this is not needed — qdbus6 handles detection."
    echo ""
fi

# ── Create virtual environment ────────────────────────────────────────────────

if [[ -d "$VENV_DIR" ]]; then
    info "Virtual environment already exists at .venv, skipping creation."
else
    info "Creating Python virtual environment in .venv …"
    python3 -m venv "$VENV_DIR"
fi

info "Installing Python dependencies …"
"$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check --upgrade pip
"$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"
info "Dependencies installed."

# ── Install systemd user service ──────────────────────────────────────────────

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/$SERVICE_NAME" << UNIT
[Unit]
Description=AFFiNE Discord Rich Presence
Documentation=file://$SCRIPT_DIR/README.md
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$VENV_DIR/bin/python -m affine_rpc.main
WorkingDirectory=$SCRIPT_DIR
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
UNIT

info "systemd user service written to $SERVICE_DIR/$SERVICE_NAME"

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"

# Try to start; may fail if graphical session is not fully up yet
if systemctl --user start "$SERVICE_NAME"; then
    info "Service started successfully."
else
    warn "Service could not start right now (will auto-start on next login)."
    warn "Check status: systemctl --user status $SERVICE_NAME"
fi

echo ""
echo "  ✔  Installation complete"
echo ""
echo "  Useful commands:"
echo "    Status : systemctl --user status  $SERVICE_NAME"
echo "    Logs   : journalctl --user -u $SERVICE_NAME -f"
echo "    Stop   : systemctl --user stop    $SERVICE_NAME"
echo "    Restart: systemctl --user restart $SERVICE_NAME"
echo ""
