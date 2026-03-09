import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

_AFFINE_STATE_FILE = Path.home() / ".config" / "AFFiNE" / "global-state.json"

# Window title format: "Document · AFFiNE"  or  "(3) Document · AFFiNE"
_TITLE_PATTERN = re.compile(r"^(?:\(\d+\) )?(.+?) · AFFiNE$")


# ── Process detection ──────────────────────────────────────────────────────────

def _is_affine_process(proc: psutil.Process) -> bool:
    try:
        name = proc.name().lower()
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline).lower()
        # Match the main Electron process (not renderer/GPU child processes)
        if "affine" not in name and "affine" not in cmdline_str:
            return False
        # Skip Electron child processes
        if "--type=" in cmdline_str:
            return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def get_affine_process() -> Optional[psutil.Process]:
    for proc in psutil.process_iter(["name", "cmdline"]):
        if _is_affine_process(proc):
            return proc
    return None


def is_affine_running() -> bool:
    return get_affine_process() is not None


def get_affine_start_time() -> Optional[float]:
    proc = get_affine_process()
    if proc:
        try:
            return proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


# ── Window title detection ─────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 3) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _try_xdotool() -> Optional[str]:
    """xdotool — works for X11 and XWayland (default for Electron apps)."""
    ids = _run(["xdotool", "search", "--name", "AFFiNE"])
    if not ids:
        return None
    for wid in ids.splitlines():
        title = _run(["xdotool", "getwindowname", wid.strip()])
        if title and "AFFiNE" in title:
            return title
    return None


def _try_wmctrl() -> Optional[str]:
    """wmctrl — alternative X11/XWayland method."""
    output = _run(["wmctrl", "-l"])
    if not output:
        return None
    for line in output.splitlines():
        # Format: WID  DESKTOP  HOST  TITLE
        parts = line.split(None, 3)
        if len(parts) >= 4 and "AFFiNE" in parts[3]:
            return parts[3]
    return None


def _try_kwin_dbus() -> Optional[str]:
    """KWin D-Bus — KDE Plasma 6 native Wayland fallback."""
    for qdbus in ("qdbus6", "qdbus"):
        # List all window object paths under /org/kde/KWin/Windows
        paths = _run([qdbus, "org.kde.KWin", "/org/kde/KWin/Windows"], timeout=5)
        if paths is None:
            continue
        for path in paths.splitlines():
            path = path.strip()
            if not path or not path.startswith("/"):
                continue
            caption = _run(
                [qdbus, "org.kde.KWin", path, "org.kde.KWin.Window.caption"],
                timeout=2,
            )
            if caption and "AFFiNE" in caption:
                return caption
        return None  # KWin reachable but no AFFiNE window found
    return None


def get_window_title() -> Optional[str]:
    """Return the current AFFiNE window title, trying multiple detection methods."""
    title = _try_xdotool()
    if title:
        return title
    title = _try_wmctrl()
    if title:
        return title
    title = _try_kwin_dbus()
    if title:
        return title
    return None


def _parse_document_from_window(title: str) -> Optional[str]:
    """Extract document name from an AFFiNE window title string."""
    if not title:
        return None
    match = _TITLE_PATTERN.match(title.strip())
    if match:
        doc = match.group(1).strip()
        return doc if doc else None
    return None


def get_document_title() -> Optional[str]:
    """Return the title of the active document in AFFiNE.

    Primary source: ~/.config/AFFiNE/global-state.json (works on Wayland).
    Fallback: window title via xdotool/wmctrl/KWin D-Bus.
    """
    # ── Primary: read from AFFiNE's state file ────────────────────────────────
    try:
        if _AFFINE_STATE_FILE.exists():
            with open(_AFFINE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            schema = state.get("tabViewsMetaSchema")
            if schema:
                active_id = schema.get("activeWorkbenchId")
                for wb in schema.get("workbenches", []):
                    if wb.get("id") != active_id:
                        continue
                    views = wb.get("views", [])
                    idx = wb.get("activeViewIndex", 0)
                    if 0 <= idx < len(views):
                        title = views[idx].get("title", "").strip()
                        if title:
                            return title
    except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        logger.debug(f"Could not read AFFiNE state file: {exc}")

    # ── Fallback: window title (X11 / XWayland) ───────────────────────────────
    win_title = get_window_title()
    if win_title:
        return _parse_document_from_window(win_title)

    return None
