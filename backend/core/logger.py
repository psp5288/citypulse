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


def setup_logger(name: str = "citypulse") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(fmt)
    stdout.setLevel(logging.INFO)
    log.addHandler(stdout)

    buf = BufferedHandler()
    buf.setLevel(logging.DEBUG)
    log.addHandler(buf)

    return log


logger = setup_logger()
