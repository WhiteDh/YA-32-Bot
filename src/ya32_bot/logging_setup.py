"""One logging setup: our package at the configured level, everything else at WARNING."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.WARNING)
    logging.getLogger("ya32_bot").setLevel(level.upper())
    logging.getLogger("aiogram.event").setLevel(logging.INFO if level.upper() == "DEBUG" else logging.WARNING)
