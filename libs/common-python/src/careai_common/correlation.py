from contextvars import ContextVar, Token
from uuid import uuid4

CORRELATION_HEADER = "x-correlation-id"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(correlation_id: str | None = None) -> Token[str | None]:
    return _correlation_id.set(correlation_id or str(uuid4()))


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def ensure_correlation_id() -> str:
    existing = get_correlation_id()
    if existing:
        return existing
    set_correlation_id()
    return get_correlation_id() or "unknown"


def clear_correlation_id(token: Token[str | None] | None = None) -> None:
    if token is not None:
        _correlation_id.reset(token)
    else:
        _correlation_id.set(None)

