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
    
    async def connect(self):
        """Connect to Redis."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"[SESSION] Connected to Redis at {self.redis_url}")
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
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
        await self.connect()
        
        session_metadata = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "message_count": 0,
            **(metadata or {})
        }
        
        # Store metadata
        meta_key = self._get_metadata_key(conversation_id)
        await self._redis.setex(
            meta_key,
            self.default_ttl,
            json.dumps(session_metadata)
        )
        
        # Initialize empty message list
        session_key = self._get_session_key(conversation_id)
        await self._redis.setex(session_key, self.default_ttl, json.dumps([]))
        
        logger.info(f"[SESSION] Created session: {conversation_id}")
        return session_metadata
    
    async def get_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get conversation history from Redis.
        
        Args:
            conversation_id: Conversation identifier
            limit: Optional limit on number of messages to return (most recent)
            
        Returns:
            List of conversation messages
        """
        await self.connect()
        
        session_key = self._get_session_key(conversation_id)
        data = await self._redis.get(session_key)
        
        if not data:
            logger.warning(f"[SESSION] No history found for: {conversation_id}")
            return []
        
        messages = json.loads(data)
        
        # Apply limit if specified
        if limit and len(messages) > limit:
            messages = messages[-limit:]
        
        logger.info(f"[SESSION] Retrieved {len(messages)} messages for: {conversation_id}")
        return messages
    
    async def add_message(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        sources: Optional[List[str]] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Add a message to conversation history.
        
        Args:
            conversation_id: Conversation identifier
            question: User's question
            answer: Assistant's answer
            sources: Optional list of source paper IDs
            context: Optional retrieved context
            metadata: Optional message metadata
            
        Returns:
            True if successful
        """
        await self.connect()
        
        session_key = self._get_session_key(conversation_id)
        
        # Get current history
        data = await self._redis.get(session_key)
        messages = json.loads(data) if data else []
        
        # Create message entry
        message = {
            "question": question,
            "answer": answer,
            "sources": sources or [],
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        
        # Add message
        messages.append(message)
        
        # Prune if too long
        if len(messages) > self.max_messages:
            logger.info(f"[SESSION] Pruning history for {conversation_id} (keeping last {self.max_messages})")
            messages = messages[-self.max_messages:]
        
        # Save back to Redis
        await self._redis.setex(
            session_key,
            self.default_ttl,
            json.dumps(messages)
        )
        
        # Update metadata
        await self._update_metadata(conversation_id, len(messages))
        
        logger.info(f"[SESSION] Added message to {conversation_id} (total: {len(messages)})")
        
        # Optional: Save to database for long-term storage
        if self.db_client:
            await self._save_to_database(conversation_id, message)
        
        return True
    
    async def _update_metadata(self, conversation_id: str, message_count: int):
        """Update session metadata."""
        meta_key = self._get_metadata_key(conversation_id)
        data = await self._redis.get(meta_key)
        
        if data:
            metadata = json.loads(data)
            metadata["last_activity"] = datetime.utcnow().isoformat()
            metadata["message_count"] = message_count
            
            await self._redis.setex(
                meta_key,
                self.default_ttl,
                json.dumps(metadata)
            )
    
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
    
    async def _save_to_database(self, conversation_id: str, message: Dict):
        """
        Optional: Save message to database for long-term storage.
        
        This method should be implemented based on your database choice.
        Example with Supabase:
        
        await self.db_client.table('conversation_messages').insert({
            'conversation_id': conversation_id,
            'question': message['question'],
            'answer': message['answer'],
            'sources': message['sources'],
            'timestamp': message['timestamp']
        }).execute()
        """
        if self.db_client:
            # TODO: Implement database insertion
            logger.debug(f"[SESSION] Saving to database: {conversation_id}")
            pass
    
    async def load_from_database(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Optional: Load conversation history from database.
        
        Useful for:
        - Recovering old conversations
        - Loading conversations that expired from Redis
        - Cross-device conversation sync
        
        Returns:
            List of messages from database
        """
        if not self.db_client:
            return []
        
        # TODO: Implement database query
        # Example with Supabase:
        # result = await self.db_client.table('conversation_messages')\
        #     .select('*')\
        #     .eq('conversation_id', conversation_id)\
        #     .order('timestamp', desc=False)\
        #     .limit(limit)\
        #     .execute()
        # return result.data
        
        logger.debug(f"[SESSION] Loading from database: {conversation_id}")
        return []
    
    async def sync_to_database(self, conversation_id: str) -> bool:
        """
        Sync entire conversation from Redis to database.
        
        Useful for:
        - Archiving important conversations
        - Before session expiry
        - User-initiated export
        """
        if not self.db_client:
            return False
        
        messages = await self.get_history(conversation_id)
        
        for message in messages:
            await self._save_to_database(conversation_id, message)
        
        logger.info(f"[SESSION] Synced {len(messages)} messages to database: {conversation_id}")
        return True


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
