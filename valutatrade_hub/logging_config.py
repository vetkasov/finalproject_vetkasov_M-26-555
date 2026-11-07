"""Ротация и формат журналов приложения."""

import logging
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from time import gmtime

from .infra.settings import SettingsLoader


def get_file_logger(name: str, level: int | str | None = None) -> logging.Logger:
    """Настроить запись в отдельный файл журнала с временем UTC."""
    settings = SettingsLoader()
    logger = logging.getLogger(f"valutatrade.{name}")
    if logger.handlers:
        return logger
    directory = settings.get("log_dir")
    directory.mkdir(parents=True, exist_ok=True)
    logger.setLevel(level if level is not None else settings.get("log_level"))
    logger.propagate = False
    handler = RotatingFileHandler(
        directory / f"{name}.log",
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backups"),
        encoding="utf-8",
    )
    formatter = logging.Formatter(settings.get("log_format"), "%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


@contextmanager
def parser_console():
    """Показывать логи парсера в консоли только во время update-rates."""
    logger = get_file_logger("parser", logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
