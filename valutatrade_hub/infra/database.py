"""Общее JSON-хранилище с атомарной заменой файлов."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, RLock

if os.name == "nt":
    import msvcrt
else:
    import fcntl


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

    @contextmanager
    def transaction(self, directory: Path):
        """Выполнить чтение и запись без вмешательства другого процесса."""
        with self._transaction_lock:
            directory.mkdir(parents=True, exist_ok=True)
            # Блокируем отдельный файл: сами JSON заменяются при записи.
            with (directory / ".valutatrade.lock").open("a+b") as lock_file:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file, fcntl.LOCK_EX)
                    yield

    def read(self, path: Path, default, *, allow_empty: bool = False):
        """Прочитать JSON, при необходимости допуская пустой файл."""
        with self._transaction_lock:
            try:
                contents = path.read_text(encoding="utf-8")
                if allow_empty and not contents.strip():
                    return default
                return json.loads(contents)
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
