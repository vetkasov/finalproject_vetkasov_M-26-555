"""Ошибки, которые основной сервис передаёт интерфейсу."""


class ValutaTradeError(Exception):
    """Базовая ошибка приложения."""


class InsufficientFundsError(ValutaTradeError):
    """В кошельке недостаточно средств для продажи."""

    def __init__(
        self, available: float, required: float, code: str, *, missing: bool = False
    ):
        message = (
            f"Недостаточно средств: доступно {available:.12g} {code}, "
            f"требуется {required:.12g} {code}"
        )
        if missing:
            message += f". Кошелёк {code!r} создаётся при первой покупке."
        super().__init__(message)


class CurrencyNotFoundError(ValutaTradeError):
    """Кода валюты нет в реестре."""

    def __init__(self, code: str, *, base: bool = False):
        currency = "базовая валюта" if base else "валюта"
        super().__init__(f"Неизвестная {currency} {code!r}")


class ApiRequestError(ValutaTradeError):
    """Внешний источник не вернул данные."""

    def __init__(self, reason: str):
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class RateUnavailableError(ValutaTradeError):
    """Для расчёта нет нужного курса."""
