"""Сценарии регистрации, торговли и просмотра курсов."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import EXCHANGE_RATES, Portfolio, User, Wallet, convert_rate
from .utils import normalize_code, read_json, validate_amount, write_json

USERS_FILE = Path("data/users.json")
PORTFOLIOS_FILE = Path("data/portfolios.json")
RATES_FILE = Path("data/rates.json")


@dataclass
class TradeResult:
    """Изменение баланса и оценка сделки в долларах."""

    currency: str
    amount: float
    before: float
    after: float
    rate: float | None
    base: str = "USD"


def _load_user(record: dict) -> User:
    return User(
        record["user_id"],
        record["username"],
        record["hashed_password"],
        record["salt"],
        datetime.fromisoformat(record["registration_date"]),
    )


def register(username: str, password: str) -> User:
    """Зарегистрировать пользователя с пустым портфелем."""
    users = read_json(USERS_FILE, [])
    portfolios = read_json(PORTFOLIOS_FILE, [])
    user_id = max((row["user_id"] for row in users + portfolios), default=0) + 1
    user = User(user_id, username, "", "", datetime.now(UTC))
    if any(row["username"] == user.username for row in users):
        raise ValueError(f"Имя пользователя {user.username!r} уже занято")
    user.change_password(password)
    portfolios.append({"user_id": user_id, "wallets": {}})
    users.append(
        user.get_user_info()
        | {"hashed_password": user.hashed_password, "salt": user.salt}
    )
    write_json(PORTFOLIOS_FILE, portfolios)
    write_json(USERS_FILE, users)
    return user


def login(username: str, password: str) -> User:
    """Проверить имя и пароль, вернуть пользователя."""
    for record in read_json(USERS_FILE, []):
        if record["username"] == username.strip():
            user = _load_user(record)
            if not user.verify_password(password):
                raise ValueError("Неверный пароль")
            return user
    raise ValueError(f"Пользователь {username!r} не найден")


def _find_portfolio(user_id: int, records: list, user: User | None = None):
    for record in records:
        if record["user_id"] == user_id:
            wallets = {
                code: Wallet(code, fields["balance"])
                for code, fields in record["wallets"].items()
            }
            return Portfolio(user_id, wallets, user), record
    raise ValueError(f"Портфель пользователя {user_id} не найден")


def _currency_code(code: str) -> str:
    code = normalize_code(code)
    if code != "USD" and f"{code}_USD" not in EXCHANGE_RATES:
        raise ValueError(f"Неизвестная валюта {code!r}")
    return code


def _rates() -> dict[str, float]:
    return EXCHANGE_RATES | {
        key: value["rate"]
        for key, value in read_json(RATES_FILE, {}).items()
        if isinstance(value, dict) and "rate" in value
    }


def show_portfolio(user_id: int, base_currency: str = "USD"):
    """Вернуть пользователя, оценки кошельков и итог в выбранной валюте."""
    base = _currency_code(base_currency)
    user = next(
        (
            _load_user(row)
            for row in read_json(USERS_FILE, [])
            if row["user_id"] == user_id
        ),
        None,
    )
    if user is None:
        raise ValueError(f"Пользователь {user_id} не найден")
    portfolio, _ = _find_portfolio(user_id, read_json(PORTFOLIOS_FILE, []), user)
    rates = _rates()
    rows = [
        (code, wallet.balance, wallet.balance * convert_rate(code, base, rates))
        for code, wallet in sorted(portfolio.wallets.items())
    ]
    return portfolio.user, base, rows, portfolio.get_total_value(base, rates)


def _trade(user_id: int, currency_code: str, amount: float, *, selling: bool):
    code = _currency_code(currency_code)
    validate_amount(amount)
    records = read_json(PORTFOLIOS_FILE, [])
    portfolio, record = _find_portfolio(user_id, records)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        if selling:
            raise ValueError(
                f"У вас нет кошелька {code!r}. Он создаётся при первой покупке."
            )
        wallet = portfolio.add_currency(code)
    before = wallet.balance
    if selling:
        wallet.withdraw(amount)
    else:
        wallet.deposit(amount)
    rate = convert_rate(code, "USD", _rates())
    record["wallets"][code] = {"balance": wallet.balance}
    write_json(PORTFOLIOS_FILE, records)
    return TradeResult(code, amount, before, wallet.balance, rate)


def buy(user_id: int, currency_code: str, amount: float) -> TradeResult:
    """Увеличить баланс валюты и оценить покупку в USD."""
    return _trade(user_id, currency_code, amount, selling=False)


def sell(user_id: int, currency_code: str, amount: float) -> TradeResult:
    """Уменьшить баланс валюты и оценить выручку в USD."""
    return _trade(user_id, currency_code, amount, selling=True)


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Вернуть курс из свежего кеша либо обновить его учебными данными."""
    source, target = _currency_code(from_code), _currency_code(to_code)
    now = datetime.now(UTC)
    if source == target:
        return 1.0, now.isoformat()
    cached = read_json(RATES_FILE, {})
    keys = [f"{code}_USD" for code in (source, target) if code != "USD"]
    if any(
        key not in cached
        or (now - datetime.fromisoformat(cached[key]["updated_at"])).total_seconds()
        > 300
        for key in keys
    ):
        cached = {
            key: {"rate": rate, "updated_at": now.isoformat()}
            for key, rate in EXCHANGE_RATES.items()
        }
        write_json(RATES_FILE, cached)
    rates = {key: value["rate"] for key, value in cached.items()}
    return convert_rate(source, target, rates), min(
        cached[key]["updated_at"] for key in keys
    )
