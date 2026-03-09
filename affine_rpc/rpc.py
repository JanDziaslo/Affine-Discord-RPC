import logging
import time
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

    # ── Discord RPC connection ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Discord IPC. Returns True on success."""
        try:
            self._presence = Presence(self.client_id)
            self._presence.connect()
            self.connected = True
            logger.info("Connected to Discord Rich Presence.")
            return True
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
