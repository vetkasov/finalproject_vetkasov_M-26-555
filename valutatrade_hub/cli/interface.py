"""Интерактивные команды ValutaTrade Hub."""

import argparse
import shlex
from datetime import datetime

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import CURRENCY_REGISTRY, CryptoCurrency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    RateUnavailableError,
    ValutaTradeError,
)
from valutatrade_hub.logging_config import parser_console
from valutatrade_hub.parser_service.updater import build_updater


class CommandHelp(Exception):
    """Справка уже напечатана парсером."""


class CommandParser(argparse.ArgumentParser):
    """Парсер, который оставляет интерактивную сессию открытой при ошибке."""

    def error(self, message: str) -> None:
        """Передать ошибку аргументов основному циклу."""
        raise ValueError(f"Ошибка команды: {message}. Введите help для справки.")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        """Завершить разбор команды, оставив программу запущенной."""
        raise CommandHelp(message)


def _build_parser() -> CommandParser:
    parser = CommandParser(prog="project")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, description in (
        ("register", "Зарегистрировать пользователя"),
        ("login", "Войти в систему"),
    ):
        command = commands.add_parser(name, help=description)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)

    portfolio = commands.add_parser("show-portfolio", help="Показать портфель")
    portfolio.add_argument("--base")

    for name, description in (
        ("buy", "Купить валюту"),
        ("sell", "Продать валюту"),
    ):
        trade = commands.add_parser(name, help=description)
        trade.add_argument("--currency", required=True)
        trade.add_argument("--amount", required=True, type=float)

    rate = commands.add_parser("get-rate", help="Посмотреть курс")
    rate.add_argument("--from", dest="from_code", required=True)
    rate.add_argument("--to", dest="to_code", required=True)
    update = commands.add_parser("update-rates", help="Обновить кеш курсов")
    update.add_argument("--source", choices=("coingecko", "exchangerate"))
    rates = commands.add_parser("show-rates", help="Показать кеш курсов")
    rates.add_argument("--currency")
    rates.add_argument("--top", type=int)
    rates.add_argument("--base")
    commands.add_parser("exit", help="Выйти из программы")
    return parser


def _format_portfolio_value(value: float, base: str) -> str:
    if isinstance(CURRENCY_REGISTRY[base], CryptoCurrency) or 0 < value < 0.01:
        return _format_rate(value)
    return f"{value:,.2f}"


def _show_portfolio(user_id: int, base_currency: str | None) -> None:
    user, base, rows, total = usecases.show_portfolio(user_id, base_currency)
    print(f"Портфель пользователя {user.username!r} (база: {base}):")
    if not rows:
        print("В портфеле пока нет кошельков.")
        return
    table = PrettyTable(["Валюта", "Баланс", f"Стоимость ({base})"])
    table.align["Баланс"] = "r"
    table.align[f"Стоимость ({base})"] = "r"
    for code, balance, value in rows:
        table.add_row([code, f"{balance:.12g}", _format_portfolio_value(value, base)])
    print(table)
    print(f"ИТОГО: {_format_portfolio_value(total, base)} {base}")


def _print_trade(command: str, trade: usecases.TradeResult) -> None:
    action = "Покупка выполнена" if command == "buy" else "Продажа выполнена"
    print(f"{action}: {trade.amount:.12g} {trade.currency}")
    print(f"{trade.currency}: было {trade.before:.12g} → стало {trade.after:.12g}")
    if trade.rate is not None:
        label = (
            "Оценочная стоимость покупки" if command == "buy" else "Оценочная выручка"
        )
        print(f"Курс: {trade.rate:.8g} {trade.base}/{trade.currency}")
        print(f"{label}: {trade.estimated_value:,.2f} {trade.base}")
    else:
        print("Оценка в USD недоступна. Выполните update-rates.")


def _format_rate(rate: float) -> str:
    return f"{rate:.8f}".rstrip("0").rstrip(".") if rate >= 1e-8 else f"{rate:.8g}"


def _format_timestamp(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S UTC")


def _show_rate(from_code: str, to_code: str) -> None:
    try:
        rate, updated_at = usecases.get_rate(from_code, to_code)
    except ApiRequestError as exc:
        raise RateUnavailableError(
            f"Курс {from_code.upper()}→{to_code.upper()} недоступен. "
            f"{exc}. Повторите позже или выполните update-rates."
        ) from exc
    source, target = from_code.upper(), to_code.upper()
    timestamp = _format_timestamp(updated_at)
    print(f"Курс {source}→{target}: {_format_rate(rate)} (обновлено: {timestamp})")
    print(f"Обратный курс {target}→{source}: {_format_rate(1 / rate)}")


def _update_rates(source: str | None) -> None:
    with parser_console():
        result = build_updater(source).run_update()
    status = "Update completed with errors" if result.errors else "Update successful"
    print(
        f"{status}. Курсов обновлено: {result.updated_count}. "
        f"Кеш обновлён: {_format_timestamp(result.last_refresh)}."
    )


def _show_rates(args: argparse.Namespace) -> None:
    base, rows = usecases.show_rates(args.currency, args.top, args.base)
    if not rows:
        print("В кеше нет курсов по выбранным фильтрам.")
        return
    table = PrettyTable(["Валюта", f"Курс ({base})", "Обновлено"])
    table.align[f"Курс ({base})"] = "r"
    for row in rows:
        table.add_row(
            [row.code, _format_rate(row.rate), _format_timestamp(row.updated_at)]
        )
    print(table)


def _print_help(parser: CommandParser, words: list[str]) -> None:
    if not words:
        parser.print_help()
        return
    parser.parse_args([words[0], "--help"])


def run() -> None:
    """Читать команды и хранить текущую сессию до выхода."""
    parser = _build_parser()
    current_user = None
    print("ValutaTrade Hub. Введите help для списка команд.")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            words = shlex.split(line)
            if not words:
                continue
            if words[0] in ("help", "--help", "-h"):
                _print_help(parser, words[1:])
                continue
            args = parser.parse_args(words)
            if args.command == "exit":
                break
            if args.command == "register":
                user = usecases.register(args.username, args.password)
                print(
                    f"Пользователь {user.username!r} "
                    f"зарегистрирован (id={user.user_id})."
                )
                print(
                    "Войдите: login --username "
                    f"{shlex.quote(user.username)} --password ****"
                )
            elif args.command == "login":
                current_user = usecases.login(args.username, args.password)
                print(f"Вы вошли как {current_user.username!r}")
            elif args.command == "get-rate":
                _show_rate(args.from_code, args.to_code)
            elif args.command == "update-rates":
                _update_rates(args.source)
            elif args.command == "show-rates":
                _show_rates(args)
            elif current_user is None:
                print("Сначала выполните login")
            elif args.command == "show-portfolio":
                _show_portfolio(current_user.user_id, args.base)
            else:
                trade = usecases.buy if args.command == "buy" else usecases.sell
                result = trade(current_user.user_id, args.currency, args.amount)
                _print_trade(args.command, result)
        except CommandHelp:
            continue
        except CurrencyNotFoundError as exc:
            print(exc)
            print(f"Поддерживаемые валюты: {', '.join(sorted(CURRENCY_REGISTRY))}")
        except ApiRequestError as exc:
            print(f"{exc}. Проверьте сеть и повторите попытку позже.")
        except (ValutaTradeError, ValueError, OSError) as exc:
            print(exc)
