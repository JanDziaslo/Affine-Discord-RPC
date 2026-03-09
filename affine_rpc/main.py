import logging
import signal
import sys
import time

from .config import load as load_config
from .monitor import (
    get_affine_start_time,
    get_document_title,
    is_affine_running,
)
from .rpc import AffineRPC

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()
    rpc = AffineRPC(config)
    poll = config["poll_interval"]

    def shutdown(sig, frame):
        logger.info("Shutting down…")
        rpc.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(f"Monitoring AFFiNE (poll interval: {poll}s). Press Ctrl+C to stop.")

    last_document: str | None = ""   # sentinel: empty string means "not yet set"
    rpc_active = False

    while True:
        try:
            running = is_affine_running()

            if running:
                # (Re-)connect to Discord if needed
                if not rpc.connected:
                    rpc.connect()

                if rpc.connected:
                    document = get_document_title()

                    # Update presence only when something changed or on first connect
                    if document != last_document or not rpc_active:
                        label = document if document else "(no title detected)"
                        logger.info(f"Active document: {label}")
                        start_time = get_affine_start_time()
                        if rpc.update(document, start_time):
                            last_document = document
                            rpc_active = True

            else:
                if rpc_active:
                    logger.info("AFFiNE closed — clearing presence.")
                    rpc.disconnect()
                    rpc_active = False
                    last_document = ""  # reset sentinel

        except Exception as exc:
            logger.error(f"Unexpected error in main loop: {exc}", exc_info=True)

        time.sleep(poll)


if __name__ == "__main__":
    main()
