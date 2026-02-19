# Architecture: Conversation History Management

## Overview

This document explains the **recommended architecture** for handling conversation history in the OpenTA Agent system. It compares different approaches and provides implementation guidance.

## The Problem

When users have multi-turn conversations with the AI agent, we need to:
1. **Store** conversation history efficiently
2. **Retrieve** it quickly on each request
3. **Maintain** context across sessions
4. **Clean up** old/inactive conversations
5. **Scale** to many concurrent users

## Architecture Options

### Option 1: Pure Redis (Recommended for Most Cases) ⭐

**Architecture:**
```
Client Request → API → Redis → Get History → LLM → Response → Save to Redis
                 ↓
            (on session end)
                 ↓
            PostgreSQL/Supabase (optional long-term storage)
```

**Pros:**
- ✅ **Very fast** (in-memory, microsecond latency)
- ✅ **Built-in TTL** (automatic cleanup)
- ✅ **Simple** to implement
- ✅ **Scalable** (can handle millions of sessions)
- ✅ **Good for real-time** chat applications

**Cons:**
- ❌ Data lost on Redis restart (mitigated by Redis persistence)
- ❌ Not ideal for long-term archival (need periodic sync to DB)

**Best for:**
- Real-time chat applications
- Sessions that are typically short (< 1 hour to few hours)
- High-traffic applications
- When speed is critical

**Implementation:**
```python
from app.services.session_manager import get_session_manager

# In your route
session_manager = get_session_manager()

# Get history
history = await session_manager.get_history(conversation_id)

# Pass to LLM
result = await rag_service.chat(query, history=history)

# Save response (if not incognito)
if not meta_params.is_incognito:
    await session_manager.add_message(
        conversation_id,
        question=query,
        answer=result["answer"],
        sources=result["sources"]
    )
```

---

### Option 2: Hybrid Redis + Database (Recommended for Production) 🚀

**Architecture:**
```
                    ┌─────────────────────────────────┐
                    │   Client Request                │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │   API Server                    │
                    │   - Check if conversation_id    │
                    │     exists in Redis             │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │   Redis (Active Sessions)       │
                    │   - TTL: 1-24 hours             │
                    │   - Fast access                 │
                    │   - Auto cleanup                │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │   Pass history to LLM           │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │   Save response:                │
                    │   1. Update Redis (fast)        │
                    │   2. Async save to DB (durable) │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │   PostgreSQL/Supabase           │
                    │   - Long-term storage           │
                    │   - Analytics                   │
                    │   - User history                │
                    └─────────────────────────────────┘
```

**Pros:**
- ✅ **Fast** (Redis for active sessions)
- ✅ **Durable** (database for long-term)
- ✅ **Scalable** (best of both worlds)
- ✅ **Analytics-friendly** (query DB for insights)
- ✅ **Recovery** (can reload from DB if Redis fails)

**Cons:**
- ❌ More complex to implement
- ❌ Two systems to maintain

**Best for:**
- **Production applications** ⭐
- When you need conversation analytics
- When users need conversation history across devices
- Long-term retention requirements

**Implementation:**
```python
from app.services.session_manager import get_session_manager

session_manager = get_session_manager()

# Try Redis first
history = await session_manager.get_history(conversation_id)

# If not in Redis (expired), try database
if not history:
    history = await session_manager.load_from_database(conversation_id)
    # Restore to Redis for future requests
    if history:
        for msg in history:
            await session_manager.add_message(
                conversation_id,
                question=msg["question"],
                answer=msg["answer"],
                sources=msg.get("sources", [])
            )

# Use history with LLM
result = await rag_service.chat(query, history=history)

# Save to both Redis and DB
await session_manager.add_message(
    conversation_id,
    question=query,
    answer=result["answer"],
    sources=result["sources"]
)
# DB save happens automatically in add_message if db_client is configured
```

---

### Option 3: Database Only

**Architecture:**
```
Client Request → API → PostgreSQL/Supabase → Get History → LLM → Response → Save to DB
```

**Pros:**
- ✅ Simple (one system)
- ✅ Durable (all data persisted)
- ✅ Good for analytics

**Cons:**
- ❌ **Slower** (10-100x slower than Redis)
- ❌ **Higher DB load** (every request hits DB)
- ❌ **No automatic cleanup** (need cron jobs)
- ❌ **Scaling challenges** at high traffic

**Best for:**
- Low-traffic applications
- MVP/prototype phase
- When simplicity > speed

**Not recommended for:**
- High-traffic applications
- Real-time chat
- When latency matters

---

### Option 4: In-Memory Only (Client-Side)

**Architecture:**
```
Client maintains history → Send with each request → LLM → Response → Client updates history
```

**Pros:**
- ✅ No server storage needed
- ✅ Simple backend

**Cons:**
- ❌ **Lost on browser refresh**
- ❌ **Not cross-device**
- ❌ **Privacy concerns** (history in client)
- ❌ **Large payloads** (send full history each time)

**Best for:**
- Incognito mode
- Privacy-sensitive applications
- Very simple prototypes

---

## Recommended Architecture: Hybrid Approach

For your OpenTA Agent, I recommend **Option 2: Hybrid Redis + Supabase**.

### Why?

1. **You already have Supabase** for papers → easy to add conversations table
2. **Students need history** across devices (study sessions)
3. **Analytics value** (popular topics, usage patterns)
4. **Performance matters** (real-time chat experience)

### Implementation Strategy

#### Phase 1: Redis for Active Sessions (Immediate)

```python
# app/services/session_manager.py already implements this
session_manager = SessionManager(
    redis_url="redis://localhost:6379",
    default_ttl=3600,  # 1 hour
    max_messages_per_session=50
)
```

**Timeline:** 1-2 days
**Effort:** Low
**Value:** High (fast, scalable)

#### Phase 2: Add Database Long-Term Storage (Next)

```sql
-- Supabase migration
CREATE TABLE conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT UNIQUE NOT NULL,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    metadata JSONB,
    is_archived BOOLEAN DEFAULT FALSE
);

CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT NOT NULL REFERENCES conversation_sessions(conversation_id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources TEXT[],
    context TEXT,
    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_conversation_messages_conv_id ON conversation_messages(conversation_id);
CREATE INDEX idx_conversation_messages_timestamp ON conversation_messages(timestamp);
```

**Timeline:** 2-3 days
**Effort:** Medium
**Value:** High (durability, analytics)

#### Phase 3: Sync Strategy

**Automatic Background Sync:**
```python
# In session_manager.py
async def add_message(self, conversation_id, question, answer, sources):
    # 1. Save to Redis (fast)
    await self._save_to_redis(conversation_id, question, answer, sources)
    
    # 2. Async save to database (durable)
    if self.db_client:
        # Fire-and-forget async task
        asyncio.create_task(
            self._save_to_database(conversation_id, {
                "question": question,
                "answer": answer,
                "sources": sources,
                "timestamp": datetime.utcnow().isoformat()
            })
        )
```

**Periodic Batch Sync:**
```python
# Background worker (run every 5 minutes)
async def sync_active_sessions_to_db():
    """Sync all active Redis sessions to database."""
    session_manager = get_session_manager()
    
    # Get all active conversation IDs from Redis
    keys = await redis.keys("conversation:*")
    
    for key in keys:
        conversation_id = key.split(":")[1]
        await session_manager.sync_to_database(conversation_id)
```

---

## Data Flow Examples

### Example 1: New Conversation

```
1. Client sends first message
   POST /chat/basic
   {
     "query": "What is machine learning?",
     "meta_params": {
       "conversation_id": null  // First message
     }
   }

2. API generates new conversation_id
   conversation_id = uuid.uuid4()

3. Create session in Redis
   await session_manager.create_session(conversation_id)

4. Process with LLM (no history)
   result = await rag_service.chat(query, history=[])

5. Save first message
   await session_manager.add_message(
       conversation_id,
       question="What is machine learning?",
       answer=result["answer"],
       sources=result["sources"]
   )

6. Return response with conversation_id
   {
     "answer": "...",
     "sources": [...],
     "conversation_id": "abc-123-def"
   }
```

### Example 2: Follow-up Message

```
1. Client sends follow-up with conversation_id
   POST /chat/basic
   {
     "query": "Tell me more about that",
     "meta_params": {
       "conversation_id": "abc-123-def"
     }
   }

2. Load history from Redis (fast!)
   history = await session_manager.get_history("abc-123-def")
   // Returns: [
   //   {
   //     "question": "What is machine learning?",
   //     "answer": "Machine learning is...",
   //     "sources": ["paper_1"]
   //   }
   // ]

3. Process with LLM + history
   result = await rag_service.chat(query, history=history)

4. Save new message
   await session_manager.add_message(
       "abc-123-def",
       question="Tell me more about that",
       answer=result["answer"],
       sources=result["sources"]
   )

5. Return response
   {
     "answer": "...",
     "sources": [...]
   }
```

### Example 3: Incognito Mode

```
1. Client sends message with is_incognito=true
   POST /chat/basic
   {
     "query": "What is AI?",
     "meta_params": {
       "is_incognito": true
     }
   }

2. Process normally but DON'T save
   result = await rag_service.chat(query, history=[])
   
   // Skip: session_manager.add_message()

3. Return response
   {
     "answer": "...",
     "conversation_id": null  // No ID for incognito
   }
```

---

## Configuration

### Environment Variables

```bash
# .env

# Redis Configuration
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_redis_password  # if using Redis Cloud
SESSION_TTL=3600  # 1 hour in seconds
MAX_MESSAGES_PER_SESSION=50

# Database Configuration (optional but recommended)
DATABASE_URL=postgresql://user:pass@localhost:5432/openta
# or use existing Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key

# Session Settings
AUTO_SYNC_TO_DB=true  # Sync to DB automatically
SYNC_INTERVAL=300  # Sync every 5 minutes
PRUNE_HISTORY_TO=20  # Keep only last 20 messages in memory
```

### Redis Setup Options

**Option A: Local Redis (Development)**
```bash
# Using Docker
docker run -d -p 6379:6379 redis:alpine

# Or install locally
brew install redis  # macOS
sudo apt install redis  # Ubuntu
```

**Option B: Redis Cloud (Production)**
```bash
# Free tier: https://redis.com/try-free/
# - 30MB storage
# - Good for ~1000-2000 active sessions
# - $0/month

REDIS_URL=redis://default:password@redis-xxxxx.cloud.redislabs.com:12345
```

**Option C: Upstash (Serverless)**
```bash
# https://upstash.com/
# - Serverless Redis
# - Pay-per-request
# - Free tier: 10k requests/day

REDIS_URL=https://xxxxx.upstash.io
UPSTASH_TOKEN=your_token
```

---

## Performance Considerations

### Latency Comparison

| Operation | Redis | PostgreSQL | Supabase |
|-----------|-------|------------|----------|
| Get History (10 msgs) | **1-5ms** | 20-50ms | 50-100ms |
| Save Message | **<1ms** | 10-30ms | 30-80ms |
| Concurrent Users | **10k+** | 1k-5k | 1k-5k |

### Token Usage Optimization

```python
# Bad: Send all history every time
history = await session_manager.get_history(conversation_id)  # 50 messages
# → 25K tokens in context!

# Good: Limit history
history = await session_manager.get_history(conversation_id, limit=10)  # Last 10
# → 5K tokens

# Better: Smart pruning
history = await session_manager.get_history(conversation_id)
history = prune_history_by_relevance(history, current_query, max_tokens=3000)
# → Only relevant messages, ~3K tokens
```

### Memory Usage

```python
# Redis memory calculation
# Average message: ~1KB (question + answer + metadata)
# 1000 active sessions × 50 messages × 1KB = 50MB
# 10k active sessions = 500MB
# 100k active sessions = 5GB

# Set appropriate TTL based on your traffic
if daily_active_users < 1000:
    SESSION_TTL = 86400  # 24 hours
elif daily_active_users < 10000:
    SESSION_TTL = 3600   # 1 hour
else:
    SESSION_TTL = 1800   # 30 minutes
```

---

## Scaling Strategy

### Small Scale (< 1k users)
- Single Redis instance
- Async DB sync
- Basic monitoring

### Medium Scale (1k-10k users)
- Redis with persistence
- Connection pooling
- Dedicated DB for conversations
- Redis Cluster if needed

### Large Scale (10k+ users)
- Redis Cluster (horizontal scaling)
- Read replicas for database
- CDN for static assets
- Load balancer
- Background job queue for DB sync

---

## Monitoring & Observability

### Key Metrics

```python
# In session_manager.py
import logging
from prometheus_client import Counter, Histogram

# Metrics
session_created = Counter('sessions_created_total', 'Total sessions created')
history_retrieved = Counter('history_retrieved_total', 'Total history retrievals')
message_saved = Counter('messages_saved_total', 'Total messages saved')
history_latency = Histogram('history_latency_seconds', 'History retrieval latency')

async def get_history(self, conversation_id: str):
    with history_latency.time():
        history = await self._redis.get(f"conversation:{conversation_id}")
        history_retrieved.inc()
        return history
```

### Health Checks

```python
# app/api/routes/health.py
@router.get("/health/sessions")
async def health_sessions():
    """Check session manager health."""
    session_manager = get_session_manager()
    
    try:
        # Test Redis connection
        await session_manager._redis.ping()
        redis_healthy = True
    except:
        redis_healthy = False
    
    # Get stats
    active_sessions = await session_manager._redis.dbsize()
    
    return {
        "redis_healthy": redis_healthy,
        "active_sessions": active_sessions,
        "status": "healthy" if redis_healthy else "degraded"
    }
```

---

## Security Considerations

### 1. Conversation Access Control

```python
async def get_history(self, conversation_id: str, user_id: str):
    """Get history with access control."""
    metadata = await self.get_metadata(conversation_id)
    
    # Verify ownership
    if metadata and metadata.get("user_id") != user_id:
        raise PermissionError("Unauthorized access to conversation")
    
    return await self._get_history_internal(conversation_id)
```

### 2. Data Encryption

```python
# Encrypt sensitive data before storing
from cryptography.fernet import Fernet

class SessionManager:
    def __init__(self, encryption_key: Optional[str] = None):
        self.cipher = Fernet(encryption_key) if encryption_key else None
    
    async def add_message(self, conversation_id, question, answer, ...):
        if self.cipher:
            question = self.cipher.encrypt(question.encode()).decode()
            answer = self.cipher.encrypt(answer.encode()).decode()
        # ... save to Redis
```

### 3. Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/chat/basic")
@limiter.limit("30/minute")  # 30 requests per minute
async def chat_basic(request: ChatRequest):
    # ... your code
```

---

## Best Practices Summary

✅ **DO:**
1. Use Redis for active sessions (speed)
2. Sync to database for durability
3. Set appropriate TTLs (1-24 hours)
4. Limit history to recent messages (10-20)
5. Use incognito mode for sensitive queries
6. Monitor Redis memory usage
7. Implement graceful fallback (Redis → DB)
8. Encrypt sensitive conversations

❌ **DON'T:**
1. Store entire conversation history in Redis indefinitely
2. Skip database sync for important conversations
3. Send unlimited history to LLM (token waste)
4. Ignore session cleanup (memory leak)
5. Mix conversations from different users
6. Store passwords or sensitive data unencrypted

---

## Migration Path

### Current State
You have: Basic history support (passed in request)

### Step 1: Add Redis (This Week)
- Set up local Redis
- Implement SessionManager
- Update chat routes
- Test with existing API

### Step 2: Add Database Sync (Next Week)
- Create Supabase tables
- Implement DB sync in SessionManager
- Background sync job
- Analytics queries

### Step 3: Optimize (Ongoing)
- Monitor performance
- Adjust TTLs based on usage
- Implement smart history pruning
- Add caching layers

---

## Conclusion

**Recommended Architecture:** Hybrid Redis + Supabase

**Why:** Best balance of speed, durability, and features for your use case.

**Next Steps:**
1. Set up Redis (locally or cloud)
2. Enable SessionManager in your routes
3. Test with conversation flow
4. Add database sync when ready

This architecture will scale from 10 users to 10,000+ users without major refactoring! 🚀
