"""Сценарии регистрации, торговли и просмотра курсов."""

from dataclasses import dataclass
from datetime import UTC, datetime

from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

from .currencies import get_currency
from .exceptions import CurrencyNotFoundError, InsufficientFundsError, ValutaTradeError
from .models import EXCHANGE_RATES, Portfolio, User, Wallet, convert_rate
from .utils import parse_utc, utc_now, validate_amount


@dataclass
class TradeResult:
    """Изменение баланса и оценка сделки в долларах."""

    currency: str
    amount: float
    before: float
    after: float
    rate: float | None
    base: str = "USD"

    @property
    def estimated_value(self) -> float | None:
        """Вернуть оценку сделки, если известен курс."""
        return None if self.rate is None else self.amount * self.rate


def _read(key: str, default):
    return DatabaseManager().read(SettingsLoader().data_path(key), default)


def _write(key: str, value) -> None:
    DatabaseManager().write(SettingsLoader().data_path(key), value)


def _load_user(record: dict) -> User:
    return User(
        record["user_id"],
        record["username"],
        record["hashed_password"],
        record["salt"],
        parse_utc(record["registration_date"]),
    )


def register(username: str, password: str) -> User:
    """Зарегистрировать пользователя с пустым портфелем."""
    with DatabaseManager().transaction():
        users = _read("users_file", [])
        user_id = max((row["user_id"] for row in users), default=0) + 1
        user = User(user_id, username, "", "", datetime.now(UTC))
        if any(row["username"] == user.username for row in users):
            raise ValutaTradeError(f"Имя пользователя {user.username!r} уже занято")
        user.change_password(password)
        portfolios = _read("portfolios_file", [])
        updated = [row for row in portfolios if row["user_id"] != user_id]
        updated.append({"user_id": user_id, "wallets": {}})
        users.append(
            user.get_user_info()
            | {"hashed_password": user.hashed_password, "salt": user.salt}
        )
        _write("portfolios_file", updated)
        try:
            _write("users_file", users)
        except OSError:
            _write("portfolios_file", portfolios)
            raise
    return user


def login(username: str, password: str) -> User:
    """Проверить имя и пароль, вернуть пользователя."""
    for record in _read("users_file", []):
        if record["username"] == username.strip():
            user = _load_user(record)
            if not user.verify_password(password):
                raise ValutaTradeError("Неверный пароль")
            return user
    raise ValutaTradeError(f"Пользователь {username!r} не найден")


def _find_portfolio(user_id: int, records: list, user: User | None = None):
    for record in records:
        if record["user_id"] == user_id:
            wallets = {
                code: Wallet(code, fields["balance"])
                for code, fields in record["wallets"].items()
            }
            return Portfolio(user_id, wallets, user), record
    raise ValutaTradeError(f"Портфель пользователя {user_id} не найден")


def _base_code(base_currency: str | None) -> str:
    code = (
        SettingsLoader().get("default_base_currency")
        if base_currency is None
        else base_currency
    )
    try:
        return get_currency(code).code
    except CurrencyNotFoundError:
        raise CurrencyNotFoundError(code, base=True) from None


def _rates() -> dict[str, float]:
    return EXCHANGE_RATES | {
        key: value["rate"]
        for key, value in _read("rates_file", {}).items()
        if isinstance(value, dict) and "rate" in value
    }


def show_portfolio(user_id: int, base_currency: str | None = None):
    """Вернуть пользователя, оценки кошельков и итог в выбранной валюте."""
    base = _base_code(base_currency)
    user = next(
        (
            _load_user(row)
            for row in _read("users_file", [])
            if row["user_id"] == user_id
        ),
        None,
    )
    if user is None:
        raise ValutaTradeError(f"Пользователь {user_id} не найден")
    portfolio, _ = _find_portfolio(user_id, _read("portfolios_file", []), user)
    rates = _rates()
    rows = [
        (code, wallet.balance, wallet.balance * convert_rate(code, base, rates))
        for code, wallet in sorted(portfolio.wallets.items())
    ]
    return portfolio.user, base, rows, portfolio.get_total_value(base, rates)


def _trade(
    user_id: int, currency_code: str, amount: float, *, selling: bool
) -> TradeResult:
    code = get_currency(currency_code).code
    validate_amount(amount)
    with DatabaseManager().transaction():
        records = _read("portfolios_file", [])
        portfolio, record = _find_portfolio(user_id, records)
        wallet = portfolio.get_wallet(code)
        if wallet is None:
            if selling:
                raise InsufficientFundsError(0, amount, code, missing=True)
            wallet = portfolio.add_currency(code)
        before = wallet.balance
        if selling:
            wallet.withdraw(amount)
        else:
            wallet.deposit(amount)
        rate = convert_rate(code, "USD", _rates())
        record["wallets"][code] = {"balance": wallet.balance}
        _write("portfolios_file", records)
    return TradeResult(code, amount, before, wallet.balance, rate)


@log_action("BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount: float) -> TradeResult:
    """Увеличить баланс валюты и оценить покупку в USD."""
    return _trade(user_id, currency_code, amount, selling=False)


@log_action("SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount: float) -> TradeResult:
    """Уменьшить баланс валюты и оценить выручку в USD."""
    return _trade(user_id, currency_code, amount, selling=True)


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Вернуть курс из свежего кеша либо обновить его учебными данными."""
    source, target = get_currency(from_code).code, get_currency(to_code).code
    if source == target:
        return 1.0, utc_now()
    now = datetime.now(UTC)
    ttl = SettingsLoader().get("rates_ttl_seconds")
    keys = [f"{code}_USD" for code in (source, target) if code != "USD"]
    with DatabaseManager().transaction():
        cached = _read("rates_file", {})
        if any(
            key not in cached
            or (now - parse_utc(cached[key]["updated_at"])).total_seconds() >= ttl
            for key in keys
        ):
            timestamp = utc_now()
            cached = {
                key: {"rate": rate, "updated_at": timestamp}
                for key, rate in EXCHANGE_RATES.items()
            }
            _write("rates_file", cached)
    rates = {key: value["rate"] for key, value in cached.items()}
    timestamp = min((cached[key]["updated_at"] for key in keys), key=parse_utc)
    return convert_rate(source, target, rates), timestamp
