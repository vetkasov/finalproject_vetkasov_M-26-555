"""Проверки входных данных и представление времени в UTC."""

import math
import re
from datetime import UTC, datetime


def normalize_code(code: str) -> str:
    """Проверить и привести код валюты к верхнему регистру."""
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{2,5}", code):
        raise ValueError(f"Некорректный код валюты: {code!r}")
    return code.upper()


def is_finite_number(value: object) -> bool:
    """Проверить, что значение — конечное число, пригодное для расчётов."""
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_amount(amount: float) -> None:
    """Отклонить неположительную или некорректную сумму."""
    if not is_finite_number(amount) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")


def utc_now() -> str:
    """Вернуть текущее время в формате ISO с суффиксом Z."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    """Прочитать ISO-дату, считая старые записи без зоны временем UTC."""
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
