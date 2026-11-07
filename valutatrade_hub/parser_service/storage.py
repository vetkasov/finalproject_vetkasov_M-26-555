"""Актуальный снимок курсов и история измерений."""

from pathlib import Path

from valutatrade_hub.core.utils import is_finite_number, parse_utc
from valutatrade_hub.infra.database import DatabaseManager

from .config import ParserConfig


def read_snapshot(path: Path) -> dict:
    """Прочитать кеш, считая отсутствующий или пустой файл пустым снимком."""
    snapshot = DatabaseManager().read(path, {}, allow_empty=True)
    message = f"Некорректный формат кеша курсов в {path}"
    if not isinstance(snapshot, dict):
        raise ValueError(message)
    if "pairs" not in snapshot and snapshot.keys() - {"last_refresh"}:
        raise ValueError(message)
    pairs = snapshot.get("pairs", {})
    last_refresh = snapshot.get("last_refresh")
    if not isinstance(pairs, dict) or (pairs and last_refresh is None):
        raise ValueError(message)
    try:
        if last_refresh is not None:
            parse_utc(last_refresh)
        for entry in pairs.values():
            rate = entry["rate"]
            if not is_finite_number(rate) or rate <= 0:
                raise ValueError
            parse_utc(entry["updated_at"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(message) from None
    return {"pairs": pairs, "last_refresh": last_refresh}


class RatesStorage:
    """Обновить два JSON-файла с сохранением истории и прежних курсов."""

    def __init__(self, config: ParserConfig):
        self._config = config
        self._database = DatabaseManager()

    def save(self, measurements: list[dict], refreshed_at: str) -> tuple[int, str]:
        """Добавить измерения и вернуть число обновлённых пар и время снимка."""
        rates_path = self._config.RATES_FILE_PATH
        history_path = self._config.HISTORY_FILE_PATH
        with self._database.transaction(rates_path.parent):
            snapshot = read_snapshot(rates_path)
            pairs = snapshot["pairs"]
            history = self._database.read(history_path, [])
            ids = {entry["id"] for entry in history}
            updated = set()
            new_history = []
            for entry in measurements:
                key = f"{entry['from_currency']}_{entry['to_currency']}"
                timestamp = entry["timestamp"]
                if entry["id"] not in ids:
                    new_history.append(entry)
                    ids.add(entry["id"])
                if key not in pairs or parse_utc(timestamp) > parse_utc(
                    pairs[key]["updated_at"]
                ):
                    pairs[key] = {
                        "rate": entry["rate"],
                        "updated_at": timestamp,
                        "source": entry["source"],
                    }
                    updated.add(key)
            if new_history:
                self._database.write(history_path, history + new_history)
            previous_refresh = snapshot.get("last_refresh") or refreshed_at
            last_refresh = max(previous_refresh, refreshed_at, key=parse_utc)
            self._database.write(
                rates_path, {"pairs": pairs, "last_refresh": last_refresh}
            )
        return len(updated), last_refresh
