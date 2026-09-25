"""Lightweight in-process rate limiting.

A fixed-window counter per client key (IP, optionally combined with a
route name) is enough for a single-instance modular monolith and avoids
pulling in a heavier limiter library. If Omniscient is later scaled
horizontally, back this with Redis instead of swapping the whole
approach.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        window_start = now - window_seconds
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.pop(0)
        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
            )
        hits.append(now)


_rate_limiter = RateLimiter()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_default_rate_limit(request: Request) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    _rate_limiter.check(f"default:{_client_key(request)}", limit=settings.rate_limit_default_per_minute)


def enforce_chat_rate_limit(request: Request) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    _rate_limiter.check(f"chat:{_client_key(request)}", limit=settings.rate_limit_chat_per_minute)
