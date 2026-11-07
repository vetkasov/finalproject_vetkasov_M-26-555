"""Модели пользователя, кошелька и портфеля."""

from datetime import datetime
from decimal import Decimal
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_hex

from .utils import is_finite_number, normalize_code, validate_amount

PASSWORD_ITERATIONS = 600_000
EXCHANGE_RATES = {
    "EUR_USD": 1.0786,
    "GBP_USD": 1.2361,
    "RUB_USD": 0.01016,
    "BTC_USD": 59337.21,
    "ETH_USD": 3720.00,
    "SOL_USD": 145.12,
}


def convert_rate(from_code: str, to_code: str, rates: dict[str, float]) -> float:
    """Получить курс между валютами через их стоимость в USD."""
    if from_code == to_code:
        return 1.0
    try:
        source = 1.0 if from_code == "USD" else rates[f"{from_code}_USD"]
        target = 1.0 if to_code == "USD" else rates[f"{to_code}_USD"]
    except KeyError as exc:
        raise ValueError(f"Не найден курс для {exc.args[0].replace('_', '→')}") from exc
    return source / target


class User:
    """Пользователь с паролем, хешированным PBKDF2-HMAC-SHA256 с солью."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        """Идентификатор пользователя."""
        return self._user_id

    @property
    def username(self) -> str:
        """Имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Хеш пароля для хранения."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Соль для проверки пароля."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Дата регистрации."""
        return self._registration_date

    def get_user_info(self) -> dict:
        """Вернуть сведения о пользователе без данных для проверки пароля."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def _hash(self, password: str) -> str:
        return pbkdf2_hmac(
            "sha256", password.encode(), self.salt.encode(), PASSWORD_ITERATIONS
        ).hex()

    def change_password(self, new_password: str) -> None:
        """Заменить пароль, сгенерировав новую соль."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        self._salt = token_hex(16)
        self._hashed_password = self._hash(new_password)

    def verify_password(self, password: str) -> bool:
        """Проверить введённый пароль."""
        return isinstance(password, str) and compare_digest(
            self.hashed_password, self._hash(password)
        )


class Wallet:
    """Баланс одной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = normalize_code(currency_code)
        self.balance = balance

    @property
    def balance(self) -> float:
        """Текущий баланс кошелька."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if not is_finite_number(value) or value < 0:
            raise ValueError("Баланс должен быть неотрицательным числом")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Увеличить баланс на положительную сумму."""
        validate_amount(amount)
        self.balance = float(Decimal(str(self.balance)) + Decimal(str(amount)))

    def withdraw(self, amount: float) -> None:
        """Списать сумму, если средств достаточно."""
        validate_amount(amount)
        if amount > self.balance:
            raise ValueError(
                f"Недостаточно средств: доступно "
                f"{self.balance:g} {self.currency_code}, "
                f"требуется {amount:g} {self.currency_code}"
            )
        self.balance = float(Decimal(str(self.balance)) - Decimal(str(amount)))

    def get_balance_info(self) -> str:
        """Вернуть баланс с кодом валюты."""
        return f"{self.balance:.12g} {self.currency_code}"


class Portfolio:
    """Кошельки одного пользователя."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ):
        self._user_id = user_id
        self._wallets = dict(wallets or {})
        self._user = user

    @property
    def user_id(self) -> int:
        """Идентификатор владельца."""
        return self._user_id

    @property
    def user(self) -> User | None:
        """Вернуть объект владельца, если он был передан."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Вернуть копию словаря кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Создать кошелёк для валюты, которой ещё нет в портфеле."""
        code = normalize_code(currency_code)
        if code in self._wallets:
            raise ValueError(f"Кошелёк {code!r} уже существует")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Найти кошелёк по коду валюты."""
        return self._wallets.get(normalize_code(currency_code))

    def get_total_value(
        self, base_currency: str = "USD", rates: dict[str, float] | None = None
    ) -> float:
        """Оценить портфель по переданным или учебным курсам."""
        base = normalize_code(base_currency)
        rates = EXCHANGE_RATES if rates is None else rates
        return sum(
            (
                wallet.balance * convert_rate(code, base, rates)
                for code, wallet in self._wallets.items()
                if wallet.balance
            ),
            0.0,
        )
