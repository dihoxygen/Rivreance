"""Structured-ish logging setup shared by the ETL entry points."""

from __future__ import annotations

import logging
import os


def configure_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=(level or os.getenv("RIVREANCE_LOG_LEVEL", "INFO")).upper(),
        format="%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
