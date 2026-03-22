import logging
import os
import time
from glob import glob
from pathlib import Path
from typing import Optional

from pypresence import Presence
from pypresence.exceptions import (
    DiscordError,
    DiscordNotFound,
    InvalidID,
    PipeClosed,
)

logger = logging.getLogger(__name__)


class AffineRPC:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.client_id = str(config["client_id"])
        self._presence: Optional[Presence] = None
        self.connected = False
        self._active_runtime_dir: Optional[str] = None

    def _candidate_runtime_dirs(self) -> list[str]:
        """Return possible runtime directories that may contain Discord IPC."""
        dirs: list[str] = []

        # Prefer explicit runtime dir first.
        env_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        if env_runtime:
            dirs.append(env_runtime)

        # Common defaults.
        dirs.append(f"/run/user/{os.getuid()}")

        # Discover IPC sockets directly and add their parent directories.
        socket_patterns = [
            "/run/user/*/discord-ipc-*",
            "/run/user/*/app/*/discord-ipc-*",  # Flatpak-style location
            "/tmp/discord-ipc-*",
        ]
        for pattern in socket_patterns:
            for path in glob(pattern):
                dirs.append(str(Path(path).parent))

        # Also consider all user runtime dirs as last resort.
        for p in Path("/run/user").glob("*"):
            if p.is_dir():
                dirs.append(str(p))

        # De-duplicate while preserving order.
        unique: list[str] = []
        seen: set[str] = set()
        for d in dirs:
            if d in seen:
                continue
            if Path(d).exists():
                seen.add(d)
                unique.append(d)
        return unique

    # ── Discord RPC connection ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Discord IPC. Returns True on success."""
        original_runtime = os.environ.get("XDG_RUNTIME_DIR")

        # Try a previously working runtime dir first.
        candidates = self._candidate_runtime_dirs()
        if self._active_runtime_dir and self._active_runtime_dir in candidates:
            candidates.remove(self._active_runtime_dir)
            candidates.insert(0, self._active_runtime_dir)

        try:
            for runtime_dir in candidates:
                os.environ["XDG_RUNTIME_DIR"] = runtime_dir
                try:
                    presence = Presence(self.client_id)
                    presence.connect()
                    self._presence = presence
                    self.connected = True
                    self._active_runtime_dir = runtime_dir
                    logger.info(
                        f"Connected to Discord Rich Presence (runtime: {runtime_dir})."
                    )
                    return True
                except DiscordNotFound:
                    continue
                except (PipeClosed, DiscordError):
                    continue

            self._presence = None
            self.connected = False
            if original_runtime is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = original_runtime
            logger.debug("Discord IPC not available yet.")
            return False
        except DiscordNotFound:
            logger.debug("Discord client is not running.")
            self._presence = None
            return False
        except InvalidID:
            logger.error(
                f"Invalid client_id '{self.client_id}'. "
                "Check the value in config.yaml."
            )
            self._presence = None
            return False
        except Exception as exc:
            logger.debug(f"Could not connect to Discord: {exc}")
            self._presence = None
            return False

    def update(self, document: Optional[str], start_time: Optional[float]) -> bool:
        """Update Discord Rich Presence. Returns False if connection was lost."""
        if not self.connected or not self._presence:
            return False

        cfg = self.config
        if document:
            details = f"{cfg['details_prefix']} {document}"
            state: Optional[str] = cfg["state_text"]
        else:
            details = cfg["idle_text"]
            state = None

        kwargs: dict = {
            "large_image": cfg.get("large_image_url") or cfg.get("large_image_key", "affine"),
            "large_text": "AFFiNE",
            "details": details,
        }
        if state:
            kwargs["state"] = state
        if start_time is not None:
            kwargs["start"] = int(start_time)

        try:
            self._presence.update(**kwargs)
            return True
        except (PipeClosed, DiscordError, InvalidID) as exc:
            logger.warning(f"Discord RPC error: {exc}")
            self.connected = False
            return False
        except Exception as exc:
            logger.warning(f"Unexpected RPC error: {exc}")
            self.connected = False
            return False

    def clear(self) -> None:
        """Clear Discord Rich Presence."""
        if self._presence and self.connected:
            try:
                self._presence.clear()
            except Exception:
                pass

    def disconnect(self) -> None:
        """Clear presence and close the IPC connection."""
        self.clear()
        time.sleep(0.5)  # give Discord time to process the clear before closing
        if self._presence:
            try:
                self._presence.close()
            except Exception:
                pass
        self._presence = None
        self.connected = False
