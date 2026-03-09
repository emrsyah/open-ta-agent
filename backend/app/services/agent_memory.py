"""
AgentMemory — Simple Redis-only conversation history for the Research Agent.

Design goals (deliberately minimal):
- Redis is the only backend. No DB fallback, no dual-write complexity.
- If Redis is unavailable the agent runs without history (graceful degradation).
- Each conversation key holds a JSON list of {role, content} message dicts.
- History is capped at the last MAX_TURNS turns before being passed to the agent.
- TTL of 24 h keeps Redis lean without manual cleanup.

History format stored in Redis (matches LangChain message format):
  [
    {"role": "user",      "content": "find papers about NLP"},
    {"role": "assistant", "content": "Here are the papers I found …",
     "sources": [ … ]},
    ...
  ]
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from redis import asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Conversation key TTL (seconds)
_TTL = 86_400  # 24 hours
# Maximum turns kept per conversation (each turn = 1 user + 1 assistant message)
MAX_TURNS = 10


def _history_key(conv_id: str) -> str:
    return f"agent:history:{conv_id}"


class AgentMemory:
    """
    Thin Redis wrapper for per-conversation message history.

    All public methods are safe to call even when Redis is down —
    they log a warning and return/do nothing instead of raising.
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Connection (lazy, best-effort)
    # ------------------------------------------------------------------

    async def _get_client(self) -> Optional[aioredis.Redis]:
        """Return an connected Redis client, or None if unavailable."""
        if self._client is not None:
            try:
                await self._client.ping()
                return self._client
            except Exception:
                self._client = None  # stale connection, recreate below

        try:
            client = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await client.ping()
            self._client = client
            return self._client
        except Exception as exc:
            logger.warning("[AGENT-MEMORY] Redis unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_history(self, conv_id: str) -> list[dict]:
        """
        Return the last MAX_TURNS * 2 messages for *conv_id*.

        Each message is a dict: {"role": "user"|"assistant", "content": str}
        plus an optional "sources" list on assistant messages.

        Returns [] if conv_id is unknown or Redis is down.
        """
        client = await self._get_client()
        if client is None:
            return []

        try:
            raw = await client.get(_history_key(conv_id))
            if not raw:
                return []
            messages: list[dict] = json.loads(raw)
            # Keep only last MAX_TURNS turns (2 messages per turn)
            cap = MAX_TURNS * 2
            if len(messages) > cap:
                messages = messages[-cap:]
            return messages
        except Exception as exc:
            logger.warning("[AGENT-MEMORY] get_history failed for %s: %s", conv_id, exc)
            return []

    async def save_turn(
        self,
        conv_id: str,
        question: str,
        answer: str,
        sources: list | None = None,
    ) -> None:
        """
        Append a user/assistant turn to the conversation history in Redis.

        This is fire-and-forget: failures are logged but never raised.
        """
        client = await self._get_client()
        if client is None:
            return

        try:
            key = _history_key(conv_id)
            raw = await client.get(key)
            messages: list[dict] = json.loads(raw) if raw else []

            messages.append({"role": "user", "content": question})
            messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources or [],
            })

            # Trim to keep only the last MAX_TURNS turns
            cap = MAX_TURNS * 2
            if len(messages) > cap:
                messages = messages[-cap:]

            await client.setex(key, _TTL, json.dumps(messages, ensure_ascii=False))
            logger.debug("[AGENT-MEMORY] Saved turn for %s (total msgs: %d)", conv_id, len(messages))
        except Exception as exc:
            logger.warning("[AGENT-MEMORY] save_turn failed for %s: %s", conv_id, exc)

    async def delete(self, conv_id: str) -> None:
        """Delete a conversation (e.g. for incognito cleanup)."""
        client = await self._get_client()
        if client is None:
            return
        try:
            await client.delete(_history_key(conv_id))
        except Exception as exc:
            logger.warning("[AGENT-MEMORY] delete failed for %s: %s", conv_id, exc)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_agent_memory: AgentMemory | None = None


def get_agent_memory() -> AgentMemory:
    """Return the global AgentMemory instance (created on first call)."""
    global _agent_memory
    if _agent_memory is None:
        settings = get_settings()
        _agent_memory = AgentMemory(redis_url=settings.REDIS_URL)
    return _agent_memory
