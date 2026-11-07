"""Журналирование операций с кошельками."""

from functools import wraps
from inspect import signature

from .logging_config import get_file_logger


def log_action(action: str, *, verbose: bool = False):
    """Записать итог сделки, при необходимости добавив изменение баланса."""

    def decorate(operation):
        parameters = signature(operation)

        @wraps(operation)
        def wrapped(*args, **kwargs):
            logger = get_file_logger("actions")
            fields = parameters.bind(*args, **kwargs).arguments
            context = (
                f"{action} user_id={fields['user_id']} "
                f"currency={fields['currency_code']!r} amount={fields['amount']!r}"
            )
            try:
                result = operation(*args, **kwargs)
            except Exception as exc:
                logger.info(
                    "%s result=ERROR error_type=%s error_message=%r",
                    context,
                    type(exc).__name__,
                    str(exc),
                )
                raise
            if result.rate is not None:
                context += f" rate={result.rate:.12g} base={result.base!r}"
            if verbose:
                context += f" before={result.before:.12g} after={result.after:.12g}"
            logger.info("%s result=OK", context)
            return result

        return wrapped

    return decorate
