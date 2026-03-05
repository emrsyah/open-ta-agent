"""
Session Manager for Conversation History

This module handles storing and retrieving conversation history using Redis
for active sessions and optionally PostgreSQL/Supabase for long-term storage.

Architecture:
- Redis: Fast access for active conversations (TTL-based)
- Database: Long-term storage for important conversations
- Hybrid: Best of both worlds
"""

import json
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from redis import asyncio as aioredis

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages conversation sessions with Redis and optional database backend.
    
    Features:
    - Fast Redis storage for active sessions
    - Automatic TTL (time-to-live) for cleanup
    - Optional long-term storage in database
    - Session pruning (keep only recent N messages)
    - Incognito mode support (no persistence)
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = 3600,  # 1 hour
        max_messages_per_session: int = 50,
        db_client = None  # Optional Supabase/PostgreSQL client
    ):
        """
        Initialize session manager.
        
        Args:
            redis_url: Redis connection URL
            default_ttl: Default TTL for sessions in seconds (default: 1 hour)
            max_messages_per_session: Maximum messages to keep per session
            db_client: Optional database client for long-term storage
        """
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.max_messages = max_messages_per_session
        self.db_client = db_client
        self._redis: Optional[aioredis.Redis] = None
    
    async def connect(self) -> bool:
        """Connect to Redis. Returns False if Redis is unavailable (DB-only mode)."""
        if self._redis is not None:
            return True
        try:
            client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=10,  # Increased for cloud Redis (Upstash)
            )
            await client.ping()
            self._redis = client
            logger.info("[SESSION] Connected to Redis at %s", self.redis_url)
            return True
        except Exception as e:
            logger.warning("[SESSION] Redis unavailable (%s). Running in DB-only mode.", e)
            self._redis = None
            return False
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None
            logger.info("[SESSION] Disconnected from Redis")
    
    def _get_session_key(self, conversation_id: str) -> str:
        """Get Redis key for conversation."""
        return f"conversation:{conversation_id}"
    
    def _get_metadata_key(self, conversation_id: str) -> str:
        """Get Redis key for conversation metadata."""
        return f"conversation:meta:{conversation_id}"
    
    async def create_session(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Create a new conversation session.
        
        Args:
            conversation_id: Unique conversation identifier
            user_id: Optional user identifier
            metadata: Optional metadata (timezone, language, etc.)
            
        Returns:
            Session metadata dict
        """
        redis_ok = await self.connect()

        session_metadata = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "message_count": 0,
            **(metadata or {})
        }

        if redis_ok:
            try:
                meta_key = self._get_metadata_key(conversation_id)
                await self._redis.setex(meta_key, self.default_ttl, json.dumps(session_metadata))
                session_key = self._get_session_key(conversation_id)
                await self._redis.setex(session_key, self.default_ttl, json.dumps([]))
            except Exception as e:
                logger.warning("[SESSION] Redis create_session failed: %s", e)
                self._redis = None

        logger.info("[SESSION] Created session: %s", conversation_id)
        return session_metadata
    
    async def get_history(
            self,
            conversation_id: str,
            limit: Optional[int] = None,
            user_id: Optional[str] = None,
        ) -> List[Dict]:
            """Get conversation history. Falls back to DB when Redis is unavailable."""
            redis_ok = await self.connect()
    
            if not redis_ok:
                return await self.load_from_database(conversation_id, limit=limit or self.max_messages, user_id=user_id)
    
            try:
                session_key = self._get_session_key(conversation_id)
                data = await self._redis.get(session_key)
    
                if not data:
                    logger.info("[SESSION] Redis miss for %s — loading from DB", conversation_id)
                    messages = await self.load_from_database(conversation_id, limit=limit or self.max_messages, user_id=user_id)
                    if messages:
                        await self._redis.setex(session_key, self.default_ttl, json.dumps(messages))
                    return messages
    
                messages = json.loads(data)
                if limit and len(messages) > limit:
                    messages = messages[-limit:]
    
                logger.info("[SESSION] Retrieved %d messages for: %s", len(messages), conversation_id)
                return messages
            except Exception as e:
                logger.warning("[SESSION] Redis get failed, falling back to DB: %s", e)
                self._redis = None
                return await self.load_from_database(conversation_id, limit=limit or self.max_messages, user_id=user_id)
    
    async def add_message(
            self,
            conversation_id: str,
            question: str,
            answer: str,
            sources: Optional[List[str]] = None,
            context: Optional[str] = None,
            metadata: Optional[Dict] = None,
            user_id: Optional[str] = None,
        ) -> bool:
            """Add a message to history. Persists to DB always; Redis is best-effort."""
            message = {
                "question": question,
                "answer": answer,
                "sources": sources or [],
                "context": context,
                "timestamp": datetime.utcnow().isoformat(),
                **(metadata or {})
            }
    
            redis_ok = await self.connect()
    
            if redis_ok:
                try:
                    session_key = self._get_session_key(conversation_id)
                    data = await self._redis.get(session_key)
                    messages = json.loads(data) if data else []
                    messages.append(message)
                    if len(messages) > self.max_messages:
                        messages = messages[-self.max_messages:]
                    await self._redis.setex(session_key, self.default_ttl, json.dumps(messages))
                    await self._update_metadata(conversation_id, len(messages))
                    logger.info("[SESSION] Added message to %s (total: %d)", conversation_id, len(messages))
                except Exception as e:
                    logger.warning("[SESSION] Redis write failed: %s. Persisting to DB only.", e)
                    self._redis = None
    
            # Always persist to DB regardless of Redis state
            await self._save_to_database(conversation_id, message, user_id=user_id)
            return True
    
    async def _update_metadata(self, conversation_id: str, message_count: int):
        """Update session metadata in Redis (best-effort)."""
        if self._redis is None:
            return
        try:
            meta_key = self._get_metadata_key(conversation_id)
            data = await self._redis.get(meta_key)
            if data:
                metadata = json.loads(data)
                metadata["last_activity"] = datetime.utcnow().isoformat()
                metadata["message_count"] = message_count
                await self._redis.setex(meta_key, self.default_ttl, json.dumps(metadata))
        except Exception:
            pass
    
    async def get_metadata(self, conversation_id: str) -> Optional[Dict]:
        """Get conversation metadata."""
        await self.connect()
        
        meta_key = self._get_metadata_key(conversation_id)
        data = await self._redis.get(meta_key)
        
        if data:
            return json.loads(data)
        return None
    
    async def delete_session(self, conversation_id: str) -> bool:
        """
        Delete a conversation session (for incognito or cleanup).
        
        Args:
            conversation_id: Conversation identifier
            
        Returns:
            True if deleted
        """
        await self.connect()
        
        session_key = self._get_session_key(conversation_id)
        meta_key = self._get_metadata_key(conversation_id)
        
        deleted = await self._redis.delete(session_key, meta_key)
        
        logger.info(f"[SESSION] Deleted session: {conversation_id}")
        return deleted > 0
    
    async def extend_ttl(self, conversation_id: str, extra_seconds: int = 3600):
        """Extend session TTL."""
        await self.connect()
        
        session_key = self._get_session_key(conversation_id)
        meta_key = self._get_metadata_key(conversation_id)
        
        await self._redis.expire(session_key, self.default_ttl + extra_seconds)
        await self._redis.expire(meta_key, self.default_ttl + extra_seconds)
        
        logger.info(f"[SESSION] Extended TTL for {conversation_id}")
    
    async def prune_history(
        self,
        conversation_id: str,
        keep_last_n: int = 10
    ) -> int:
        """
        Prune conversation history to keep only recent messages.
        
        Args:
            conversation_id: Conversation identifier
            keep_last_n: Number of recent messages to keep
            
        Returns:
            Number of messages removed
        """
        await self.connect()
        
        session_key = self._get_session_key(conversation_id)
        data = await self._redis.get(session_key)
        
        if not data:
            return 0
        
        messages = json.loads(data)
        original_count = len(messages)
        
        if original_count > keep_last_n:
            messages = messages[-keep_last_n:]
            await self._redis.setex(
                session_key,
                self.default_ttl,
                json.dumps(messages)
            )
            removed = original_count - keep_last_n
            logger.info(f"[SESSION] Pruned {removed} messages from {conversation_id}")
            return removed
        
        return 0
    
    async def _save_to_database(
            self, conversation_id: str, message: Dict, user_id: Optional[str] = None
        ) -> None:
            """Persist a single message turn to Supabase via ConversationCRUD."""
            from app.database import get_session_factory
            from app.db.crud import ConversationCRUD
    
            factory = get_session_factory()
            if factory is None:
                return
    
            try:
                async with factory() as session:
                    crud = ConversationCRUD(session)
                    # Ensure conversation row exists
                    await crud.upsert_conversation(
                        conversation_id=conversation_id,
                        title=message.get("title"),
                        is_incognito=message.get("is_incognito", False),
                        user_id=user_id,
                    )
                    await crud.add_message(
                        conversation_id=conversation_id,
                        question=message["question"],
                        answer=message["answer"],
                        sources=message.get("sources"),
                        search_query=message.get("search_query"),
                    )
                logger.debug("[SESSION] Persisted message to DB for conversation: %s", conversation_id)
            except Exception as e:
                logger.warning("[SESSION] DB save failed for %s: %s", conversation_id, e)

    async def load_from_database(
            self, conversation_id: str, limit: int = 50, user_id: Optional[str] = None
        ) -> List[Dict]:
            """
            Load conversation history from Supabase.
            Called when Redis has no entry (expired or first load on new instance).
            """
            from app.database import get_session_factory
            from app.db.crud import ConversationCRUD
    
            factory = get_session_factory()
            if factory is None:
                return []
    
            try:
                async with factory() as session:
                    crud = ConversationCRUD(session)
                    # Verify ownership if user_id provided
                    conv = await crud.get_conversation(conversation_id, user_id=user_id)
                    if not conv:
                        logger.warning("[SESSION] Conversation not found or access denied: %s", conversation_id)
                        return []
                    messages = await crud.get_messages(conversation_id, limit=limit)
                    result = [
                        {
                            "question": m.question,
                            "answer": m.answer,
                            "sources": m.sources or [],
                            "search_query": m.search_query,
                            "timestamp": m.created_at.isoformat(),
                        }
                        for m in messages
                    ]
                logger.info("[SESSION] Loaded %d messages from DB for: %s", len(result), conversation_id)
                return result
            except Exception as e:
                logger.warning("[SESSION] DB load failed for %s: %s", conversation_id, e)
                return []

    async def sync_to_database(self, conversation_id: str) -> bool:
        """Sync all Redis messages for a conversation to the database."""
        messages = await self.get_history(conversation_id)
        for message in messages:
            await self._save_to_database(conversation_id, message)
        logger.info("[SESSION] Synced %d messages to DB: %s", len(messages), conversation_id)
        return True

    # ── Session Papers Tracking (for context-aware planning) ───────────────
    
    def _get_session_papers_key(self, conversation_id: str) -> str:
        """Get Redis key for session papers."""
        return f"session_papers:{conversation_id}"
    
    def _get_last_answer_key(self, conversation_id: str) -> str:
        """Get Redis key for last answer."""
        return f"last_answer:{conversation_id}"
    
    async def get_session_papers(self, conversation_id: str) -> List[Dict]:
        """Get all papers retrieved in this conversation.
        
        Returns papers with citation_number for [1], [2], etc. references.
        This is used by the planner to enable contextual follow-up questions
        like "compare [1] and [2]" without new retrieval.
        """
        redis_ok = await self.connect()
        
        if not redis_ok:
            # Fallback: extract papers from message history
            messages = await self.load_from_database(conversation_id, limit=self.max_messages)
            return self._extract_papers_from_messages(messages)
        
        try:
            key = self._get_session_papers_key(conversation_id)
            data = await self._redis.get(key)
            
            if not data:
                # Try to extract from message history
                messages = await self.load_from_database(conversation_id, limit=self.max_messages)
                papers = self._extract_papers_from_messages(messages)
                if papers:
                    await self._redis.setex(key, self.default_ttl, json.dumps(papers))
                return papers
            
            papers = json.loads(data)
            logger.info("[SESSION] Retrieved %d session papers for: %s", len(papers), conversation_id)
            return papers
            
        except Exception as e:
            logger.warning("[SESSION] Failed to get session papers: %s", e)
            return []
    
    async def add_session_papers(
        self, 
        conversation_id: str, 
        papers: List[Dict]
    ) -> bool:
        """Add papers to the session cache.
        
        Papers are deduplicated by ID and assigned citation numbers.
        """
        if not papers:
            return True
            
        redis_ok = await self.connect()
        
        if not redis_ok:
            return False
        
        try:
            key = self._get_session_papers_key(conversation_id)
            existing_data = await self._redis.get(key)
            existing_papers = json.loads(existing_data) if existing_data else []
            
            # Deduplicate by ID
            existing_ids = {p.get("id") for p in existing_papers}
            
            for paper in papers:
                if paper.get("id") not in existing_ids:
                    # Assign citation number
                    paper["citation_number"] = len(existing_papers) + 1
                    existing_papers.append(paper)
                    existing_ids.add(paper.get("id"))
            
            # Re-number all papers to ensure sequential citation numbers
            for i, paper in enumerate(existing_papers, 1):
                paper["citation_number"] = i
            
            await self._redis.setex(key, self.default_ttl, json.dumps(existing_papers))
            logger.info("[SESSION] Added %d papers to session (total: %d)", len(papers), len(existing_papers))
            return True
            
        except Exception as e:
            logger.warning("[SESSION] Failed to add session papers: %s", e)
            return False
    
    async def get_last_answer(self, conversation_id: str) -> str:
        """Get the last answer from this conversation for context."""
        redis_ok = await self.connect()
        
        if not redis_ok:
            messages = await self.load_from_database(conversation_id, limit=1)
            return messages[-1].get("answer", "") if messages else ""
        
        try:
            key = self._get_last_answer_key(conversation_id)
            data = await self._redis.get(key)
            return data or ""
        except Exception as e:
            logger.warning("[SESSION] Failed to get last answer: %s", e)
            return ""
    
    async def set_last_answer(
        self, 
        conversation_id: str, 
        answer: str,
        sources: List[Dict] = None
    ) -> bool:
        """Store the last answer and update session papers from sources."""
        redis_ok = await self.connect()
        
        if not redis_ok:
            return False
        
        try:
            key = self._get_last_answer_key(conversation_id)
            await self._redis.setex(key, self.default_ttl, answer)
            
            # Also update session papers from sources
            if sources:
                await self.add_session_papers(conversation_id, sources)
            
            return True
        except Exception as e:
            logger.warning("[SESSION] Failed to set last answer: %s", e)
            return False
    
    def _extract_papers_from_messages(self, messages: List[Dict]) -> List[Dict]:
        """Extract unique papers from message history."""
        all_papers = []
        seen_ids = set()
        
        for msg in messages:
            sources = msg.get("sources", [])
            for paper in sources:
                if isinstance(paper, dict) and paper.get("id") not in seen_ids:
                    all_papers.append(paper)
                    seen_ids.add(paper.get("id"))
        
        # Assign citation numbers
        for i, paper in enumerate(all_papers, 1):
            paper["citation_number"] = i
        
        return all_papers

# Global instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager instance."""
    global _session_manager
    if _session_manager is None:
        # Initialize with environment variables
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        default_ttl = int(os.getenv("SESSION_TTL", "3600"))
        max_messages = int(os.getenv("MAX_MESSAGES_PER_SESSION", "50"))
        
        _session_manager = SessionManager(
            redis_url=redis_url,
            default_ttl=default_ttl,
            max_messages_per_session=max_messages
        )
    return _session_manager


async def init_session_manager(
    redis_url: str = "redis://localhost:6379",
    default_ttl: int = 3600,
    max_messages: int = 50,
    db_client = None
) -> SessionManager:
    """
    Initialize the global session manager.
    
    Args:
        redis_url: Redis connection URL
        default_ttl: Default TTL in seconds
        max_messages: Max messages per session
        db_client: Optional database client
        
    Returns:
        Initialized SessionManager
    """
    global _session_manager
    _session_manager = SessionManager(
        redis_url=redis_url,
        default_ttl=default_ttl,
        max_messages_per_session=max_messages,
        db_client=db_client
    )
    await _session_manager.connect()
    return _session_manager
