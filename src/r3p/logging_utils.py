"""Logging and run-directory helpers.

Every experiment writes to ``outputs/<experiment>/<timestamp>/``:

- ``log.txt``       : full experiment log
- ``metrics.json``  : numeric results (written by the experiment itself)
- ``*.png``         : visualizations
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def create_run_dir(output_root: str | Path, experiment_name: str) -> Path:
    """Create ``output_root/experiment_name/<YYYYmmdd-HHMMSS>/`` and return it."""
    run_dir = Path(output_root) / experiment_name / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def setup_logger(run_dir: str | Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configure the ``r3p`` logger with console + optional file output."""
    logger = logging.getLogger("r3p")
    logger.setLevel(level)
    logger.propagate = False
    # Reset handlers so repeated setup (tests, multiple runs) does not duplicate lines.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if run_dir is not None:
        file_handler = logging.FileHandler(Path(run_dir) / "log.txt", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    return logger
