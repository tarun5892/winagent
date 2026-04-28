"""Thread-safe logging that fans out to console and the GUI log panel."""
from __future__ import annotations

import logging
import queue
from logging.handlers import QueueHandler

LOG_QUEUE: queue.Queue[logging.LogRecord] = queue.Queue(-1)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("winagent")
    if root.handlers:
        return root
    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    qh = QueueHandler(LOG_QUEUE)
    root.addHandler(console)
    root.addHandler(qh)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"winagent.{name}")
