"""Logger configuration for the voice assistant (package local).

This mirrors the top-level `logger.py` so backend package imports `app.logger` reliably
when the app is started from the `backend` directory.
"""

import logging
import sys
import os
import tomllib
from pathlib import Path

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def _get_configured_log_level(config_path: str = "config.toml") -> int:
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return logging.DEBUG

    level_name = str(config.get("logging", {}).get("level", "DEBUG")).upper()
    return getattr(logging, level_name, logging.DEBUG)


LOG_LEVEL = _get_configured_log_level()

# Logger setup
logger = logging.getLogger("voice_assistant")
logger.setLevel(LOG_LEVEL)


# Prevent adding multiple handlers if the module is imported multiple times
if not logger.handlers:
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(LOG_DIR / "voice_assistant.log")
    file_handler.setLevel(LOG_LEVEL)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(filename)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Avoid duplicate logs propagating to root logger
    logger.propagate = False


def suppress_warnings():
    """Suppress unwanted warnings from third-party libraries."""
    # Suppress HuggingFace Hub warnings
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

    # Suppress specific warnings
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
    warnings.filterwarnings(
        "ignore",
        message="dropout option adds dropout after all but last recurrent layer.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=".*weight_norm.*deprecated.*",
        category=FutureWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message="words count mismatch.*",
    )


def get_logger():
    """Get the configured logger instance."""
    return logger
