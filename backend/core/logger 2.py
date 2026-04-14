import logging
import sys
from datetime import datetime, timezone

LOG_BUFFER: list[dict] = []
MAX_LOG_BUFFER = 300


class BufferedHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        LOG_BUFFER.append(entry)
        if len(LOG_BUFFER) > MAX_LOG_BUFFER:
            LOG_BUFFER.pop(0)


def setup_logging():
    """Attach ring buffer to root logger so /api/logs sees app + uvicorn lines."""
    root = logging.getLogger()
    if any(isinstance(h, BufferedHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    h = BufferedHandler()
    h.setLevel(logging.DEBUG)
    root.addHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    if not any(isinstance(x, logging.StreamHandler) for x in root.handlers if x is not h):
        root.addHandler(sh)


setup_logging()

logger = logging.getLogger("citypulse")
