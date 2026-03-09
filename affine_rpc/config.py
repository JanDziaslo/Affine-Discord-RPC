import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"
LOGO_FILE = PROJECT_ROOT / "affine.webp"
CACHE_DIR = Path.home() / ".cache" / "affine-discord-rpc"
ASSET_UPLOAD_FLAG = CACHE_DIR / "asset_uploaded"

_DEFAULTS = {
    "poll_interval": 5,
    "large_image_key": "affine",
    "details_prefix": "📝",
    "state_text": "Edytowanie notatek",
    "idle_text": "Otwarte",
}


def load() -> dict:
    if not CONFIG_FILE.exists():
        print(
            f"ERROR: {CONFIG_FILE} not found.\n"
            "Copy config.yaml, fill in your client_id, then try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    for key, val in _DEFAULTS.items():
        data.setdefault(key, val)

    client_id = str(data.get("client_id", ""))
    if not client_id or client_id.startswith("REPLACE"):
        print(
            "ERROR: 'client_id' is not configured in config.yaml.\n"
            "See README.md → step 1 for how to get your Discord Application ID.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ensure client_id is stored as a string (YAML may parse it as int)
    data["client_id"] = client_id
    return data
