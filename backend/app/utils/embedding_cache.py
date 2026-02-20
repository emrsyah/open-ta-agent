"""
Redis-backed cache for Voyage AI embeddings.
Avoids redundant API calls for repeated or similar queries.
"""

import hashlib
import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 86400  # 24 hours

_redis = None


async def _get_redis():
    """Lazily connect to Redis; returns None if unavailable."""
    global _redis
    if _redis is not None:
        return _redis

    from app.config import get_settings
    redis_url = get_settings().REDIS_URL
    try:
        from redis import asyncio as aioredis
        client = await aioredis.from_url(redis_url, decode_responses=False)
        await client.ping()
        _redis = client
        logger.info("[EMBED_CACHE] Connected to Redis at %s", redis_url)
    except Exception as e:
        logger.warning("[EMBED_CACHE] Redis unavailable, embedding cache disabled: %s", e)
        _redis = None

    return _redis


def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha256(f"{model}:{text}".encode()).hexdigest()
    return f"emb:{h}"


async def get_cached_embedding(text: str, model: str) -> Optional[List[float]]:
    r = await _get_redis()
    if r is None:
        return None
    try:
        data = await r.get(_cache_key(text, model))
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("[EMBED_CACHE] Read error: %s", e)
    return None


async def cache_embedding(text: str, model: str, embedding: List[float]) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.setex(_cache_key(text, model), CACHE_TTL, json.dumps(embedding))
    except Exception as e:
        logger.warning("[EMBED_CACHE] Write error: %s", e)
