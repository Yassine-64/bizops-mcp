"""Typed failures a connector can raise. The executor's retry policy keys on these; the model only ever sees
a short structured message."""

from __future__ import annotations


class ConnectorError(Exception):
    retryable = False

    def __init__(self, message: str, *, connector: str = "") -> None:
        super().__init__(message)
        self.connector = connector


class RateLimited(ConnectorError):
    retryable = True

    def __init__(self, retry_after: float = 1.0, *, connector: str = "") -> None:
        super().__init__(f"rate limited, retry after {retry_after}s", connector=connector)
        self.retry_after = retry_after


class Timeout(ConnectorError):
    retryable = True


class CredentialExpired(ConnectorError):
    """Refreshable once per step; a second failure is final."""


class Unavailable(ConnectorError):
    retryable = True


class ConflictAfterWrite(ConnectorError):
    """The connector committed but the response was lost. Only resolvable through the operation_id."""


class NotFound(ConnectorError):
    pass


class InvalidArgument(ConnectorError):
    pass


__all__ = [
    "ConflictAfterWrite",
    "ConnectorError",
    "CredentialExpired",
    "InvalidArgument",
    "NotFound",
    "RateLimited",
    "Timeout",
    "Unavailable",
]
