"""Application-wide logging setup for Project-On."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """Initialize application-wide logging with console + rotating file output."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    logging.getLogger("PyQt6").setLevel(logging.WARNING)


def cleanup_old_crash_logs(log_dir: Path, max_count: int = 20) -> None:
    """Keep only the most recent crash log files, delete the rest."""
    if not log_dir.exists():
        return
    crash_logs = sorted(log_dir.glob("crash_*.txt"), reverse=True)
    for old_log in crash_logs[max_count:]:
        try:
            old_log.unlink()
        except OSError:
            pass
