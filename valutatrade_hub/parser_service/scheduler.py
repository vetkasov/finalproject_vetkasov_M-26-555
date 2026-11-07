"""Отдельный периодический запуск Parser Service."""

import logging
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import get_file_logger

from .config import ParserConfig
from .updater import build_updater


def run_scheduler(config: ParserConfig | None = None) -> None:
    """Обновлять курсы с интервалом из настроек до остановки процесса."""
    config = config or ParserConfig()
    updater = build_updater(config=config)
    logger = get_file_logger("parser", logging.DEBUG)
    while True:
        try:
            updater.run_update()
        except (ApiRequestError, OSError, ValueError) as exc:
            logger.error("Scheduled update failed: %s", exc)
        time.sleep(config.UPDATE_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_scheduler()
    except KeyboardInterrupt:
        pass
