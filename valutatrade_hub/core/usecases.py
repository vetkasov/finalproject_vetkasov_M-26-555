"""Сценарии регистрации, торговли и просмотра курсов."""

from dataclasses import dataclass
from datetime import UTC, datetime

from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import build_updater

from .currencies import CryptoCurrency, get_currency
from .exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    RateUnavailableError,
    ValutaTradeError,
)
from .models import Portfolio, User, Wallet, convert_rate
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


def _snapshot() -> dict:
    return _read("rates_file", {"pairs": {}, "last_refresh": None})


def _rates(pairs: dict) -> dict[str, float]:
    return {key: value["rate"] for key, value in pairs.items()}


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
    rates = _rates(_snapshot()["pairs"])
    rows = [
        (
            code,
            wallet.balance,
            wallet.balance * convert_rate(code, base, rates) if wallet.balance else 0.0,
        )
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
        try:
            rate = convert_rate(code, "USD", _rates(_snapshot()["pairs"]))
        except RateUnavailableError:
            rate = None
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


def _timestamp(pairs: dict, source: str, target: str) -> str:
    keys = {f"{code}_USD" for code in (source, target) if code != "USD"}
    return min((pairs[key]["updated_at"] for key in keys), key=parse_utc)


def _fresh(pairs: dict, source: str, target: str) -> bool:
    try:
        oldest = parse_utc(_timestamp(pairs, source, target))
    except KeyError:
        return False
    return (datetime.now(UTC) - oldest).total_seconds() < SettingsLoader().get(
        "rates_ttl_seconds"
    )


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Вернуть свежий курс, при необходимости запросив обновление у парсера."""
    source, target = get_currency(from_code).code, get_currency(to_code).code
    if source == target:
        return 1.0, utc_now()
    pairs = _snapshot()["pairs"]
    if not _fresh(pairs, source, target):
        update = build_updater().run_update()
        pairs = _snapshot()["pairs"]
        if not _fresh(pairs, source, target):
            reason = f"курс {source}→{target} недоступен или устарел"
            if update.errors:
                reason += f". {' / '.join(update.errors)}"
            raise ApiRequestError(reason)
    return convert_rate(source, target, _rates(pairs)), _timestamp(
        pairs, source, target
    )


@dataclass
class RateRow:
    """Строка таблицы кеша с курсом и временем его обновления."""

    code: str
    rate: float
    updated_at: str


def show_rates(
    currency_code: str | None = None,
    top: int | None = None,
    base_currency: str | None = None,
) -> tuple[str, list[RateRow]]:
    """Прочитать кеш и применить фильтры валюты, рейтинга и базы."""
    base = _base_code(base_currency)
    currency = None if currency_code is None else get_currency(currency_code).code
    if top is not None and top <= 0:
        raise ValueError("'top' должен быть положительным целым числом")
    snapshot = _snapshot()
    pairs = snapshot["pairs"]
    if not pairs:
        raise RateUnavailableError("Кеш курсов пуст. Сначала выполните update-rates.")
    rates = _rates(pairs)
    codes = {pair.removesuffix("_USD") for pair in pairs}
    if currency:
        codes = {currency} if currency in codes or currency == "USD" else set()
        if not codes:
            raise RateUnavailableError(
                f"Курса {currency} нет в кеше. Выполните update-rates."
            )
    if top is None:
        ordered = sorted(codes)
    else:
        crypto = (
            code for code in codes if isinstance(get_currency(code), CryptoCurrency)
        )
        ordered = sorted(crypto, key=lambda code: rates[f"{code}_USD"], reverse=True)[
            :top
        ]
    return base, [
        RateRow(
            code,
            convert_rate(code, base, rates),
            _timestamp(pairs, code, base)
            if (code, base) != ("USD", "USD")
            else snapshot["last_refresh"],
        )
        for code in ordered
    ]
