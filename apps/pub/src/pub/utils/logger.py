"""
Logger configuration
"""
import os

import logging
import logging.config


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
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "default",
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