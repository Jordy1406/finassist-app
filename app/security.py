"""Client identity, authentication and rate limiting (P4-04, findings MAN-01 and MAN-04).

- With `API_KEYS` set, every endpoint except /health needs an `X-API-Key` header; the key's name is the client
  identity, and agent sessions belong to the client that created them.
- Without `API_KEYS` (local development), requests are not authenticated and the client identity is the caller's IP
  address. The API logs a warning at start-up; never expose it like that.
- Each client gets `RATE_LIMIT_PER_MIN` requests per minute on /chat and /agent (sliding window, in memory).
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings

log = logging.getLogger("finassist.security")


def client_identity(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Return the caller's identity, or raise 401 when authentication is on and the key is missing or wrong."""
    if not settings.api_keys:
        return "ip:" + (request.client.host if request.client else "unknown")
    given = request.headers.get("x-api-key", "")
    for name, key in settings.api_keys.items():
        if given and hmac.compare_digest(given, key):
            return "key:" + name
    raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key", headers={"WWW-Authenticate": "ApiKey"})


class RateLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client: str, limit_per_min: int, now: float | None = None) -> None:
        if limit_per_min <= 0:
            return
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.hits[client]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= limit_per_min:
                raise HTTPException(status_code=429, detail="Too many requests; try again in a minute",
                                    headers={"Retry-After": "60"})
            q.append(now)


limiter = RateLimiter()


def rate_limited_client(client: str = Depends(client_identity), settings: Settings = Depends(get_settings)) -> str:
    limiter.check(client, settings.rate_limit_per_min)
    return client


def warn_if_open(settings: Settings) -> None:
    if not settings.api_keys:
        log.warning("API_KEYS is not set: the API is UNAUTHENTICATED (local development only). Anyone who can reach "
                    "it can use any session whose id they know.")
