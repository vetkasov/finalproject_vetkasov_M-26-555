"""Клиенты CoinGecko и ExchangeRate-API с единым форматом курсов."""

import logging
from abc import ABC, abstractmethod
from time import perf_counter
from typing import ClassVar

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import is_finite_number

from .config import ParserConfig

_LOGGER = logging.getLogger("valutatrade.parser")
_STATUS_ERRORS = {
    401: "проверьте ключ API",
    403: "доступ запрещён, проверьте ключ API",
    429: "исчерпан лимит запросов, повторите позже",
}
_API_ERRORS = {
    "invalid-key": "неверный ключ API",
    "inactive-account": "подтвердите аккаунт ExchangeRate-API",
    "quota-reached": "исчерпан лимит запросов, повторите позже",
    "unsupported-code": "базовая валюта не поддерживается",
    "malformed-request": "неверный формат запроса",
}


class BaseApiClient(ABC):
    """Общий интерфейс источников курсов."""

    source: ClassVar[str]

    def __init__(self, config: ParserConfig):
        self.config = config
        self.response_meta: dict = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Вернуть курсы в формате CURRENCY_USD → число."""

    def _request(self, url: str, *, safe_url: str, **kwargs) -> dict:
        _LOGGER.debug("GET %s", safe_url)
        started = perf_counter()
        try:
            response = requests.get(url, timeout=self.config.REQUEST_TIMEOUT, **kwargs)
        except requests.exceptions.Timeout:
            raise ApiRequestError(f"{self.source}: время ожидания истекло") from None
        except requests.exceptions.RequestException as exc:
            # requests может включить URL с ключом в текст ошибки.
            raise ApiRequestError(
                f"{self.source}: сетевая ошибка ({type(exc).__name__})"
            ) from None
        self.response_meta = {
            "request_ms": round((perf_counter() - started) * 1000),
            "status_code": response.status_code,
        }
        if etag := response.headers.get("ETag"):
            self.response_meta["etag"] = etag
        _LOGGER.debug("%s: %s", self.source, self.response_meta)
        if response.status_code != 200:
            status = response.status_code
            hint = _STATUS_ERRORS.get(status, "источник не вернул данные")
            raise ApiRequestError(f"{self.source}: HTTP {status}, {hint}")
        try:
            payload = response.json()
        except ValueError:
            raise ApiRequestError(f"{self.source}: ответ не является JSON") from None
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source}: ожидался объект JSON")
        return payload

    def _positive_rate(self, value: object, code: str) -> float:
        if not is_finite_number(value) or value <= 0:
            raise ApiRequestError(f"{self.source}: неверный курс для {code}")
        return float(value)


class CoinGeckoClient(BaseApiClient):
    """Загрузить курсы криптовалют к USD одним запросом."""

    source = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Вернуть цены криптовалют, сопоставив ID с тикерами."""
        config = self.config
        ids = config.CRYPTO_ID_MAP
        headers = {}
        if config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = config.COINGECKO_API_KEY
        payload = self._request(
            config.COINGECKO_URL,
            safe_url=config.COINGECKO_URL,
            params={"ids": ",".join(ids.values()), "vs_currencies": "usd"},
            headers=headers,
        )
        rates = {}
        for code, coin_id in ids.items():
            coin = payload.get(coin_id)
            price = coin.get("usd") if isinstance(coin, dict) else None
            rates[f"{code}_USD"] = self._positive_rate(price, code)
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Загрузить фиатные курсы и привести их к направлению валюта → USD."""

    source = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Вернуть стоимость единицы каждой валюты в долларах."""
        config = self.config
        key = config.EXCHANGERATE_API_KEY
        if not key:
            raise ApiRequestError(f"{self.source}: задайте EXCHANGERATE_API_KEY")
        endpoint = config.EXCHANGERATE_API_URL
        base = config.BASE_FIAT_CURRENCY
        payload = self._request(
            f"{endpoint}/{key}/latest/{base}",
            safe_url=f"{endpoint}/<key>/latest/{base}",
        )
        if payload.get("result") != "success":
            error_type = payload.get("error-type")
            reason = (
                _API_ERRORS.get(error_type, "неуспешный ответ API")
                if isinstance(error_type, str)
                else "неуспешный ответ API"
            )
            raise ApiRequestError(f"{self.source}: {reason}")
        values = payload.get("conversion_rates")
        if not isinstance(values, dict) or payload.get("base_code") != base:
            raise ApiRequestError(f"{self.source}: отсутствуют курсы для {base}")
        rates = {}
        for code in config.FIAT_CURRENCIES:
            rate = 1 / self._positive_rate(values.get(code), code)
            rates[f"{code}_USD"] = self._positive_rate(rate, code)
        return rates
