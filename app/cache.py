import hashlib
import logging

import redis.asyncio as redis

from app.config import settings

log = logging.getLogger(__name__)


class CacheClient:
    """Redis-backed async cache with graceful degradation."""

    def __init__(self, url: str = "") -> None:
        self._url = url or settings.redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        try:
            self._client = redis.from_url(self._url, decode_responses=True)
            await self._client.ping()
        except Exception:
            log.warning("Redis unavailable — caching disabled")
            self._client = None

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def get(self, key: str) -> str | None:
        if not self._client:
            return None
        try:
            return await self._client.get(key)
        except Exception:
            log.warning("Cache get failed for key=%s", key)
            return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        if not self._client:
            return
        try:
            await self._client.set(key, value, ex=ttl)
        except Exception:
            log.warning("Cache set failed for key=%s", key)

    async def invalidate(self, key: str) -> None:
        if not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception:
            log.warning("Cache invalidate failed for key=%s", key)


def cache_key(prefix: str, *parts: str) -> str:
    """Build a deterministic cache key from prefix and parts."""
    raw = ":".join(parts)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


# Singleton instance
cache = CacheClient()
