import logging
import sys
from datetime import datetime

LOG_BUFFER: list[dict] = []
MAX_LOG_BUFFER = 200


class BufferedHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        LOG_BUFFER.append(entry)
        if len(LOG_BUFFER) > MAX_LOG_BUFFER:
            LOG_BUFFER.pop(0)


def setup_logger(name: str = "citypulse") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(fmt)
    stdout.setLevel(logging.INFO)
    logger.addHandler(stdout)

    buf = BufferedHandler()
    buf.setLevel(logging.DEBUG)
    logger.addHandler(buf)

    return logger


log = setup_logger()
