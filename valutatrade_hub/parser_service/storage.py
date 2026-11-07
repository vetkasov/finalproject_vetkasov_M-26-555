"""Актуальный снимок курсов и история измерений."""

from valutatrade_hub.core.utils import parse_utc
from valutatrade_hub.infra.database import DatabaseManager

from .config import ParserConfig


class RatesStorage:
    """Обновить два JSON-файла с сохранением истории и прежних курсов."""

    def __init__(self, config: ParserConfig):
        self._config = config
        self._database = DatabaseManager()

    def save(self, measurements: list[dict], refreshed_at: str) -> tuple[int, str]:
        """Добавить измерения и вернуть число обновлённых пар и время снимка."""
        rates_path = self._config.RATES_FILE_PATH
        history_path = self._config.HISTORY_FILE_PATH
        with self._database.transaction():
            snapshot = self._database.read(rates_path, {})
            pairs = snapshot.get("pairs", {})
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
