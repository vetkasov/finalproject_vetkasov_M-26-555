"""Проверки входных данных и работа с JSON."""

import json
import math
import re
from pathlib import Path


def normalize_code(code: str) -> str:
    """Проверить и привести код валюты к верхнему регистру."""
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{2,5}", code):
        raise ValueError(f"Некорректный код валюты: {code!r}")
    return code.upper()


def is_finite_number(value: object) -> bool:
    """Проверить, что значение — конечное число, пригодное для расчётов."""
    return type(value) in (int, float) and math.isfinite(value)


def validate_amount(amount: float) -> None:
    """Отклонить неположительную или некорректную сумму."""
    if not is_finite_number(amount) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")


def read_json(path: Path, default):
    """Прочитать JSON, используя значение по умолчанию для нового файла."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    """Сохранить данные в JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
