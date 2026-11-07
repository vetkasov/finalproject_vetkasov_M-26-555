"""Настройки запросов, валют и файлов Parser Service."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from valutatrade_hub.core.currencies import CRYPTO_ID_MAP, FIAT_CODES
from valutatrade_hub.infra.settings import SettingsLoader


@dataclass(frozen=True)
class ParserConfig:
    """Параметры обоих источников и пути к кешу и истории."""

    BASE_FIAT_CURRENCY: ClassVar[str] = "USD"
    FIAT_CURRENCIES: ClassVar[tuple[str, ...]] = tuple(
        code for code in FIAT_CODES if code != "USD"
    )
    CRYPTO_CURRENCIES: ClassVar[tuple[str, ...]] = tuple(CRYPTO_ID_MAP)
    CRYPTO_ID_MAP: ClassVar[dict[str, str]] = CRYPTO_ID_MAP
    COINGECKO_URL: ClassVar[str] = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: ClassVar[str] = "https://v6.exchangerate-api.com/v6"

    EXCHANGERATE_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY"), repr=False
    )
    COINGECKO_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY"), repr=False
    )
    REQUEST_TIMEOUT: float = 10
    UPDATE_INTERVAL_SECONDS: int = 3600
    RATES_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().data_path("rates_file")
    )
    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: SettingsLoader().data_path("history_file")
    )
