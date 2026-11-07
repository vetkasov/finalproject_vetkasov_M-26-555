"""Общее JSON-хранилище с атомарной заменой файлов."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, RLock


class DatabaseManager:
    """Единый доступ к JSON для чтения и изменения данных."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._transaction_lock = RLock()
                cls._instance = instance
            return cls._instance

    def transaction(self):
        """Защитить блок чтение → изменение → запись внутри процесса."""
        return self._transaction_lock

    def read(self, path: Path, default):
        """Прочитать JSON или вернуть значение для отсутствующего файла."""
        with self._transaction_lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return default
            except json.JSONDecodeError as exc:
                raise ValueError(f"Некорректный JSON в {path}: {exc.msg}") from exc

    def write(self, path: Path, data) -> None:
        """Заменить JSON целиком после успешной записи временного файла."""
        with self._transaction_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=path.parent, delete=False
                ) as file:
                    temporary = Path(file.name)
                    json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
                    file.write("\n")
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
