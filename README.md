# AFFiNE Discord RPC

A standalone Python application that shows [Discord Rich Presence](https://discord.com/rich-presence) while using [AFFiNE](https://affine.pro/) on Linux. Tested on EndeavourOS with KDE Plasma (Wayland).

```
Discord shows:
  📝 My Document           ← active document title
  Editing notes            ← status text
  [AFFiNE logo]  AFFiNE   ← image + elapsed time
```

---

## Requirements

- AFFiNE stable (AppImage, `.deb`, or system package)
- Discord desktop client running in the background
- `qdbus6` — for window visibility detection on KDE Plasma Wayland (usually pre-installed)
- **For native install:** Python 3.10+
- **For Docker:** Docker + Docker Compose

Optional: `xdotool` or `wmctrl` as fallback for X11/XWayland setups:
```bash
sudo pacman -S xdotool
```

---

## Step 1 — Create a Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → enter a name (e.g. `AFFiNE`) → **Create**
3. Copy the **Application ID** from the *General Information* page
4. Paste it into `config.yaml` as `client_id`

---

## Installation

Two ways to run — pick one.

### Option A — Native (systemd user service)

```bash
# 1. Clone the repository
git clone https://github.com/dziaslo/Affine-Discord-RPC.git
cd Affine-Discord-RPC

# 2. Fill in config.yaml
nano config.yaml   # set client_id

# 3. Run the installer
chmod +x install.sh
./install.sh
```

The installer:
- creates a Python virtual environment in `.venv/`
- installs dependencies (`pypresence`, `psutil`, etc.)
- installs and enables a **systemd user service** (auto-starts on login)

**Service management:**
```bash
systemctl --user status  affine-discord-rpc.service   # check status
systemctl --user restart affine-discord-rpc.service   # restart
systemctl --user stop    affine-discord-rpc.service   # stop
journalctl --user -u affine-discord-rpc.service -f    # live logs
```

**Manual run (for testing):**
```bash
.venv/bin/python -m affine_rpc.main
```

---

### Option B — Docker

> **Note:** KWin D-Bus scripting is unavailable inside Docker (no access to the host session journald). Window close detection falls back to process-only — presence clears when the AFFiNE process fully exits, but **not** when the window is just closed to the system tray.

#### Pull from GHCR (pre-built image)

```bash
# 1. Clone the repository (only config.yaml and docker-compose.yml are needed)
git clone https://github.com/dziaslo/Affine-Discord-RPC.git
cd Affine-Discord-RPC

# 2. Fill in config.yaml
nano config.yaml   # set client_id

# 3. Create .env so the container UID matches your user
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env

# 4. Start
docker compose up -d
```

#### Build locally instead of pulling

```bash
docker compose up -d --build
```

The image is automatically built and pushed to `ghcr.io/dziaslo/affine-discord-rpc` on every push to `main` and on version tags (`v*.*.*`) via GitHub Actions.

**Container management:**
```bash
docker compose logs -f              # live logs
docker compose restart              # restart
docker compose down                 # stop and remove
docker compose pull && docker compose up -d   # update to latest image
```

---

## Configuration (`config.yaml`)

| Key | Description | Default |
|---|---|---|
| `client_id` | Discord Application ID | **required** |
| `large_image_url` | HTTPS URL of the logo shown in Discord | AFFiNE GitHub avatar |
| `large_image_key` | Uploaded asset name (used if `large_image_url` is not set) | `affine` |
| `poll_interval` | How often to check AFFiNE state (seconds) | `5` |
| `details_prefix` | Prefix before the document title | `📝` |
| `state_text` | Status text shown when a document is open | `Editing notes` |
| `idle_text` | Text shown when AFFiNE is open but no document is detected | `Open` |

---

## How it works

```
AFFiNE (Electron, native Wayland)
        │
        │  KWin D-Bus scripting (workspace.windowList())
        │  → detects whether AFFiNE window is open/closed
        │
        │  ~/.config/AFFiNE/global-state.json
        │  → reads active document title directly
        ▼
[affine_rpc/monitor.py]  — process + window detection, document title
        │
        ▼
[affine_rpc/rpc.py]      — pypresence → Discord IPC socket
        │                  (/run/user/1000/discord-ipc-0)
        ▼
   Discord Client         — displays Rich Presence
```

**Window detection** uses KWin's D-Bus scripting API (`workspace.windowList()`) to
check whether AFFiNE has an open, non-minimized window. This works correctly on
native **KDE Plasma Wayland** — even when AFFiNE keeps running in the system tray
after the window is closed. `xdotool`/`wmctrl` are used as a fallback on X11/XWayland.

**Document title** is read directly from `~/.config/AFFiNE/global-state.json`
(`tabViewsMetaSchema` → active workbench → active view title). No window title
parsing needed, so it works reliably on Wayland.

**Logo** is loaded from a direct HTTPS URL (AFFiNE's GitHub organization avatar
by default). No token or manual asset upload required.

---

## Troubleshooting

**Discord doesn't show Rich Presence:**
- Make sure Discord desktop client is running
- Check logs (native): `journalctl --user -u affine-discord-rpc.service -f`
- Check logs (Docker): `docker compose logs -f`
- Verify `client_id` in `config.yaml` matches your Discord Application ID

**Presence is not cleared when AFFiNE is closed:**
- **Native:** This works automatically via KWin window detection. Make sure `qdbus6` is available: `which qdbus6`
- **Docker:** KWin D-Bus is unavailable in Docker — presence only clears when the AFFiNE *process* fully exits (not when minimised to tray). This is a known limitation.

**Document title not detected:**
- AFFiNE must be running and have a document open
- Check that `~/.config/AFFiNE/global-state.json` exists and is readable
- Increase `poll_interval` in `config.yaml` if updates are too slow

**Service does not start:**
- Run `systemctl --user status affine-discord-rpc.service` for details
- Make sure `graphical-session.target` is active after login
- Try running manually first: `.venv/bin/python -m affine_rpc.main`

---

## Project structure

```
Affine-Discord-RPC/
├── affine_rpc/
│   ├── __init__.py
│   ├── config.py    # config.yaml loading and validation
│   ├── monitor.py   # process + KWin window detection, document title
│   ├── rpc.py       # pypresence wrapper
│   └── main.py      # main polling loop + signal handling
├── .github/
│   └── workflows/
│       └── docker.yml   # CI: build & push to GHCR on push/tag
├── affine.webp          # AFFiNE logo (optional, for manual asset upload)
├── config.yaml          # user configuration (excluded from git)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── install.sh           # native installer (venv + systemd service)
```

## License

MIT