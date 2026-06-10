"""
Logger configuration
"""
import os

import logging
import logging.config


class ColorFormatter(logging.Formatter):
    """ANSI color formatter for console logs."""

    COLORS = {
        logging.DEBUG: "\033[36m",  # cyan
        logging.INFO: "\033[32m",  # green
        logging.WARNING: "\033[33m",  # yellow
        logging.ERROR: "\033[31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = self.COLORS.get(record.levelno)
        if not color:
            return message
        return f"{color}{message}{self.RESET}"


def setup_logging(environment: str = "development", debug: bool = False):
    """Configure application logging.

    Args:
        environment: The environment name (e.g. "development", "production").
        debug:       Enable DEBUG level when True.
    """
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "colored": {
                "()": "pub.utils.logger.ColorFormatter",
                "format": "%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
                "datefmt": '%m-%d %H:%M:%S'
                # "datefmt": '%Y-%m-%d %H:%M:%S'
                # "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "colored",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": "logs/app.log",
            },
        },
        "root": {
            "level": "DEBUG" if debug else "INFO",
            "handlers": ["console", "file"],
        },
    }

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.config.dictConfig(logging_config)
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured for {environment} environment")
    return logger
