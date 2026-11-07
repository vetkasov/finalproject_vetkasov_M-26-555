"""Координация опроса источников и сохранения курсов."""

import logging
from dataclasses import dataclass

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now
from valutatrade_hub.logging_config import get_file_logger

from .api_clients import BaseApiClient, CoinGeckoClient, ExchangeRateApiClient
from .config import ParserConfig
from .storage import RatesStorage


@dataclass
class UpdateResult:
    """Результат обновления кеша и ошибки отдельных источников."""

    updated_count: int
    last_refresh: str
    errors: list[str]


class RatesUpdater:
    """Опросить источники и сохранить все полученные курсы."""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage):
        self._clients = clients
        self._storage = storage

    def run_update(self) -> UpdateResult:
        """Обновить курсы или сообщить о сбое всех выбранных источников."""
        logger = get_file_logger("parser", logging.DEBUG)
        logger.info("Starting rates update")
        measurements = []
        errors = []
        for client in self._clients:
            logger.info("Fetching %s...", client.source)
            try:
                rates = client.fetch_rates()
                if not rates:
                    raise ApiRequestError(f"{client.source}: нет курсов в ответе")
            except ApiRequestError as exc:
                logger.error("%s", exc)
                logger.debug("Details for %s", client.source, exc_info=True)
                errors.append(str(exc))
                continue
            timestamp = utc_now()
            for pair, rate in rates.items():
                source_code, target_code = pair.split("_")
                measurements.append(
                    {
                        "id": f"{pair}_{timestamp}",
                        "from_currency": source_code,
                        "to_currency": target_code,
                        "rate": rate,
                        "timestamp": timestamp,
                        "source": client.source,
                        "meta": client.response_meta.copy(),
                    }
                )
            logger.info("%s: received %s rates", client.source, len(rates))
        if not measurements:
            raise ApiRequestError(
                "не получены курсы ни от одного источника"
                + (". " + " / ".join(errors) if errors else "")
            )
        logger.info("Writing %s rates...", len(measurements))
        count, last_refresh = self._storage.save(measurements, utc_now())
        logger.info("Rates update finished: %s updated, %s errors", count, len(errors))
        return UpdateResult(count, last_refresh, errors)


def build_updater(
    source: str | None = None, config: ParserConfig | None = None
) -> RatesUpdater:
    """Создать обновление для всех источников или одного выбранного."""
    config = config or ParserConfig()
    factories = {"coingecko": CoinGeckoClient, "exchangerate": ExchangeRateApiClient}
    if source is not None and source not in factories:
        raise ValueError(f"Неизвестный источник {source!r}")
    selected = factories if source is None else (source,)
    clients = [factories[name](config) for name in selected]
    return RatesUpdater(clients, RatesStorage(config))
