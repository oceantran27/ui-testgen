from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


@contextmanager
def bind_log_context(**fields: Any):
    current = dict(_log_context.get({}))
    merged = dict(current)

    for key, value in fields.items():
        if value is None:
            continue
        merged[key] = value

    token = _log_context.set(merged)
    try:
        yield merged
    finally:
        _log_context.reset(token)


def get_log_context() -> dict[str, Any]:
    return dict(_log_context.get({}))


def merge_with_log_context(payload: dict[str, Any] | None = None, **extra_fields: Any) -> dict[str, Any]:
    merged = get_log_context()

    if payload:
        merged.update(payload)

    for key, value in extra_fields.items():
        if value is None:
            continue
        merged[key] = value

    return merged
