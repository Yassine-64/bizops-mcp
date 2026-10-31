"""Canonical forms used for identity: two calls with the same capability and arguments are the same intent."""

from __future__ import annotations

import json
from typing import Any


def canonical_args(args: dict[str, Any]) -> str:
    return json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


__all__ = ["canonical_args"]
