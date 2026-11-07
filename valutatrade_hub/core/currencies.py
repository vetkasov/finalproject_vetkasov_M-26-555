"""Иерархия и реестр поддерживаемых валют."""

from abc import ABC, abstractmethod

from .exceptions import CurrencyNotFoundError
from .utils import normalize_code


class Currency(ABC):
    """Общие имя, код и интерфейс отображения валюты."""

    def __init__(self, name: str, code: str):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        self.name = name.strip()
        self.code = normalize_code(code)

    @abstractmethod
    def get_display_info(self) -> str:
        """Вернуть описание валюты."""


class FiatCurrency(Currency):
    """Фиатная валюта со страной или зоной эмиссии."""

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        """Вернуть название и зону эмиссии."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и известной капитализацией."""

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    def get_display_info(self) -> str:
        """Вернуть название, алгоритм и капитализацию."""
        cap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {cap})"
        )


_FIAT = (
    FiatCurrency("US Dollar", "USD", "United States"),
    FiatCurrency("Euro", "EUR", "Eurozone"),
    FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    FiatCurrency("Russian Ruble", "RUB", "Russia"),
)
_CRYPTO = (
    (CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12), "bitcoin"),
    (CryptoCurrency("Ethereum", "ETH", "Proof of Stake", 4.47e11), "ethereum"),
    (CryptoCurrency("Solana", "SOL", "Proof of History", 6.40e10), "solana"),
)
FIAT_CODES = tuple(currency.code for currency in _FIAT)
CRYPTO_ID_MAP = {currency.code: coin_id for currency, coin_id in _CRYPTO}
CURRENCY_REGISTRY = {currency.code: currency for currency in _FIAT}
CURRENCY_REGISTRY.update({currency.code: currency for currency, _ in _CRYPTO})


def get_currency(code: str) -> Currency:
    """Найти валюту по коду или сообщить, что она не поддерживается."""
    try:
        return CURRENCY_REGISTRY[normalize_code(code)]
    except (KeyError, ValueError):
        raise CurrencyNotFoundError(code) from None
