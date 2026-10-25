"""Sliding-window rate limiter (brute-force protection on login).

Pure core (time injected) so it unit-tests deterministically. In-memory and
per-process — fine for the prototype; production should back it with Redis so the
limit holds across worker replicas.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float):
        self.max = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True


# 5 login attempts per minute per client IP.
login_limiter = RateLimiter(max_attempts=5, window_seconds=60)


def rate_limit_login(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    if not login_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; try again later.",
        )
