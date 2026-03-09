import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

_AFFINE_STATE_FILE = Path.home() / ".config" / "AFFiNE" / "global-state.json"

# Window title format: "Document · AFFiNE"  or  "(3) Document · AFFiNE"
_TITLE_PATTERN = re.compile(r"^(?:\(\d+\) )?(.+?) · AFFiNE$")

# KWin scripting state (loaded once, reused)
_kwin_script_id: Optional[str] = None
_kwin_script_path: Optional[str] = None


# ── Process detection ──────────────────────────────────────────────────────────

def _is_affine_process(proc: psutil.Process) -> bool:
    try:
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline)
        # Match only the main AFFiNE Electron process — requires app.asar in the path
        # and must NOT be a child renderer/GPU/utility process
        if "/affine/" not in cmdline_str.lower() and "affine" not in proc.name().lower():
            return False
        if "--type=" in cmdline_str:
            return False
        # Extra guard: must reference the affine app bundle, not just a path that
        # happens to contain the word (e.g. a JetBrains project path)
        has_affine_bundle = any(
            "affine" in part.lower() and (part.endswith(".asar") or "/affine/" in part.lower())
            for part in cmdline
        )
        if not has_affine_bundle:
            # Also accept if the process name itself is "affine"
            return "affine" in proc.name().lower()
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


# ── Window title detection (X11/XWayland fallback) ────────────────────────────

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
    ids = _run(["xdotool", "search", "--name", "AFFiNE"])
    if not ids:
        return None
    for wid in ids.splitlines():
        title = _run(["xdotool", "getwindowname", wid.strip()])
        if title and "AFFiNE" in title:
            return title
    return None


def _try_wmctrl() -> Optional[str]:
    output = _run(["wmctrl", "-l"])
    if not output:
        return None
    for line in output.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 4 and "AFFiNE" in parts[3]:
            return parts[3]
    return None


def get_window_title() -> Optional[str]:
    title = _try_xdotool()
    if title:
        return title
    return _try_wmctrl()


# ── KWin window visibility check (KDE Plasma 6 Wayland) ───────────────────────

_KWIN_JS = """\
var found = false;
workspace.windowList().forEach(function(w) {
    if (w.caption && w.caption.indexOf("AFFiNE") !== -1 && !w.minimized) {
        found = true;
    }
});
print("AFFINE_WIN:" + (found ? "1" : "0") + ":" + new Date().getTime());
"""


def _ensure_kwin_script() -> Optional[str]:
    """Load the KWin window-check script once; return script ID or None."""
    global _kwin_script_id, _kwin_script_path
    if _kwin_script_id is not None:
        return _kwin_script_id

    try:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, prefix="affine_rpc_kwin_"
        )
        f.write(_KWIN_JS)
        f.close()
        _kwin_script_path = f.name

        r = subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting",
             "org.kde.kwin.Scripting.loadScript", f.name, "affine_rpc_wincheck"],
            capture_output=True, text=True, timeout=3,
        )
        sid = r.stdout.strip()
        if sid is not None and (sid.isdigit() or sid == "0"):
            _kwin_script_id = sid
            logger.debug(f"KWin window-check script loaded (id={sid})")
            return sid
    except Exception as exc:
        logger.debug(f"KWin scripting not available: {exc}")
    return None


def unload_kwin_script() -> None:
    """Unload the KWin script and remove the temp file (call on shutdown)."""
    global _kwin_script_id, _kwin_script_path
    if _kwin_script_path:
        try:
            subprocess.run(
                ["qdbus6", "org.kde.KWin", "/Scripting",
                 "org.kde.kwin.Scripting.unloadScript", "affine_rpc_wincheck"],
                capture_output=True, timeout=3,
            )
        except Exception:
            pass
        try:
            os.unlink(_kwin_script_path)
        except OSError:
            pass
        _kwin_script_id = None
        _kwin_script_path = None


def has_affine_window_kwin() -> Optional[bool]:
    """Return True/False if KWin confirms AFFiNE window state; None if unavailable."""
    sid = _ensure_kwin_script()
    if sid is None:
        return None

    run_ts = int(time.time() * 1000)

    try:
        subprocess.run(
            ["qdbus6", "org.kde.KWin", f"/Scripting/Script{sid}",
             "org.kde.kwin.Script.run"],
            capture_output=True, timeout=3,
        )
    except Exception:
        return None

    time.sleep(0.25)

    try:
        j = subprocess.run(
            ["journalctl", "--user", "-u", "plasma-kwin_wayland",
             "--since", "5 seconds ago", "--no-pager", "-n", "50"],
            capture_output=True, text=True, timeout=4,
        )
        best_ts = 0
        best_result: Optional[bool] = None
        for line in j.stdout.splitlines():
            if "AFFINE_WIN:" not in line:
                continue
            # Format: "AFFINE_WIN:1:1773082778261"
            marker_idx = line.index("AFFINE_WIN:")
            parts = line[marker_idx + len("AFFINE_WIN:"):].split(":")
            if len(parts) >= 2:
                try:
                    ts = int(parts[1])
                    if ts >= run_ts and ts > best_ts:
                        best_ts = ts
                        best_result = parts[0] == "1"
                except ValueError:
                    pass
        return best_result
    except Exception as exc:
        logger.debug(f"Could not read KWin journal: {exc}")
        return None


def is_affine_window_open() -> bool:
    """
    Returns True if AFFiNE is running AND has a visible (non-minimized) window.
    Falls back to process-only check if KWin detection is unavailable.
    """
    if not is_affine_running():
        return False
    kwin_result = has_affine_window_kwin()
    if kwin_result is not None:
        return kwin_result
    # KWin unavailable — fall back to assuming window is open if process runs
    return True


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
