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
    """No response in time. The write may or may not have committed: the caller cannot tell, which is the
    whole reason operation identity exists."""

    retryable = True


class CredentialExpired(ConnectorError):
    """Refreshable once per step; a second failure is final."""


class Unavailable(ConnectorError):
    retryable = True


class NotFound(ConnectorError):
    pass


class InvalidArgument(ConnectorError):
    pass


__all__ = [
    "ConnectorError",
    "CredentialExpired",
    "InvalidArgument",
    "NotFound",
    "RateLimited",
    "Timeout",
    "Unavailable",
]
