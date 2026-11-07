"""Настройки приложения с переопределением из pyproject.toml."""

import os
import tomllib
from pathlib import Path
from threading import Lock
from typing import Any

_DEFAULTS = {
    "data_dir": "data",
    "log_dir": "logs",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "history_file": "exchange_rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_format": "%(levelname)s %(asctime)s %(name)s %(message)s",
    "log_level": "INFO",
    "log_max_bytes": 1_048_576,
    "log_backups": 3,
}


class SettingsLoader:
    """Единожды загрузить настройки для всех слоёв приложения."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        # __new__ оставляет правило единственного экземпляра внутри класса.
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._values = instance._load()
                cls._instance = instance
            return cls._instance

    @staticmethod
    def _load() -> dict:
        values = _DEFAULTS.copy()
        try:
            with Path("pyproject.toml").open("rb") as file:
                values.update(tomllib.load(file).get("tool", {}).get("valutatrade", {}))
        except FileNotFoundError:
            pass
        for key in ("data_dir", "log_dir"):
            values[key] = Path(os.getenv(f"VALUTATRADE_{key.upper()}", values[key]))
        return values

    def get(self, key: str, default: Any = None) -> Any:
        """Вернуть настройку или указанное значение по умолчанию."""
        return self._values.get(key, default)

    def data_path(self, key: str) -> Path:
        """Вернуть путь к файлу данных по ключу настройки."""
        return self.get("data_dir") / self._values[key]
