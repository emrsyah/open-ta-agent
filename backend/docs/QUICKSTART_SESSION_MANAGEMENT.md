# Quick Start: Enable Session Management

Get conversation history working in **5 minutes**! ⚡

## Prerequisites

- Backend is running
- Python dependencies installed
- Docker (optional, for local Redis)

## Step 1: Install Redis Dependency

```bash
cd backend
pip install redis[hiredis]>=5.0.0
```

## Step 2: Start Redis

### Option A: Docker (Recommended for Development)

```bash
# Start Redis container
docker run -d -p 6379:6379 --name openta-redis redis:alpine

# Verify it's running
docker ps | grep redis
```

### Option B: Cloud Redis (Recommended for Production)

**Redis Cloud (Free Tier):**
1. Sign up at https://redis.com/try-free/
2. Create a free database (30MB)
3. Copy connection URL
4. Update `.env`:
   ```bash
   REDIS_URL=redis://default:password@redis-xxxxx.cloud.redislabs.com:12345
   ```

**Upstash (Serverless):**
1. Sign up at https://upstash.com/
2. Create a Redis database
3. Copy connection URL
4. Update `.env`

### Option C: Local Installation

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
```

**Windows:**
Download from https://github.com/tporadowski/redis/releases

## Step 3: Configure Environment

Edit `.env`:

```bash
# Add these lines
REDIS_URL=redis://localhost:6379
SESSION_TTL=3600
MAX_MESSAGES_PER_SESSION=50
```

## Step 4: Enable Session Manager

Edit `app/api/routes/chat.py`:

**Find this section (~line 45):**
```python
# TODO: Load conversation history from Redis/DB using conversation_id
# For now, we'll use empty history. See session_manager.py for implementation
history = None
if conversation_id:
    # from app.services.session_manager import get_session_manager
    # session_manager = get_session_manager()
    # history = await session_manager.get_history(conversation_id)
    pass
```

**Replace with:**
```python
# Load conversation history from Redis
from app.services.session_manager import get_session_manager
session_manager = get_session_manager()

history = None
if conversation_id:
    history = await session_manager.get_history(conversation_id, limit=10)
```

**Find this section (~line 60):**
```python
# TODO: Save to history if not incognito
# if not meta_params.is_incognito and conversation_id:
#     await session_manager.add_message(
#         conversation_id,
#         question=query,
#         answer=result["answer"],
#         sources=result.get("sources", [])
#     )
```

**Replace with:**
```python
# Save to history if not incognito
if not meta_params.is_incognito and conversation_id:
    await session_manager.add_message(
        conversation_id,
        question=query,
        answer=result["answer"],
        sources=result.get("sources", [])
    )
```

## Step 5: Test It!

### Test 1: Verify Redis Connection

```bash
# If using Docker
docker exec -it openta-redis redis-cli ping
# Should return: PONG

# If using local Redis
redis-cli ping
# Should return: PONG
```

### Test 2: Start the Server

```bash
cd backend
python run.py
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Test 3: Test Conversation Flow

```bash
# Terminal 1: Send first message
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is machine learning?",
    "meta_params": {
      "stream": false,
      "conversation_id": "test_conv_123"
    }
  }'
```

**Expected response:**
```json
{
  "answer": "Machine learning is...",
  "sources": ["Paper_001"],
  ...
}
```

```bash
# Terminal 2: Send follow-up (should remember context!)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Can you give me an example?",
    "meta_params": {
      "stream": false,
      "conversation_id": "test_conv_123"
    }
  }'
```

**Expected response should reference the previous answer!**

### Test 4: Verify Redis Storage

```bash
# Check if conversation was saved
redis-cli

# In Redis CLI:
127.0.0.1:6379> KEYS conversation:*
1) "conversation:test_conv_123"
2) "conversation:meta:test_conv_123"

127.0.0.1:6379> GET conversation:test_conv_123
# Should show JSON array with conversation history

127.0.0.1:6379> exit
```

## Step 6: Run Interactive Demo

```bash
cd backend
python examples/conversation_with_session.py
```

Select a demo and see session management in action!

## Troubleshooting

### Error: "Connection refused" (Redis)

**Solution:**
```bash
# Check if Redis is running
docker ps | grep redis

# If not, start it
docker run -d -p 6379:6379 --name openta-redis redis:alpine
```

### Error: "No module named 'redis'"

**Solution:**
```bash
pip install redis[hiredis]>=5.0.0
```

### Error: "session_manager is not defined"

**Solution:** Make sure you uncommented the import line in `chat.py`:
```python
from app.services.session_manager import get_session_manager
```

### History not working

**Check:**
1. Redis is running: `redis-cli ping`
2. Session code is uncommented in `chat.py`
3. `conversation_id` is provided in requests
4. `.env` has `REDIS_URL` configured

### Debug Mode

Enable logging to see what's happening:

Edit `app/main.py`, add:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Restart server and check logs for session-related messages:
```
[SESSION] Created session: conv_123
[SESSION] Retrieved 2 messages for: conv_123
[SESSION] Added message to conv_123 (total: 3)
```

## Next Steps

### 1. Add Database Long-Term Storage (Optional)

Create table in Supabase:
```sql
CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources TEXT[],
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conv_messages_conv_id 
ON conversation_messages(conversation_id);
```

Enable in `session_manager.py`:
```python
from supabase import create_client

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

session_manager = SessionManager(
    redis_url="redis://localhost:6379",
    db_client=supabase  # Enable DB sync
)
```

### 2. Update Frontend

Use new API structure:
```typescript
const response = await fetch('/chat/basic', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: userInput,
    meta_params: {
      conversation_id: currentConversationId,
      stream: true,
      language: 'id-ID'
    }
  })
});
```

### 3. Monitor & Optimize

Check Redis memory:
```bash
redis-cli INFO memory
```

Check active sessions:
```bash
redis-cli DBSIZE
```

Set appropriate TTL based on usage:
```bash
# .env
SESSION_TTL=7200  # 2 hours for active users
```

## Configuration Options

### Redis Settings

```bash
# .env

# Connection
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_password  # if using auth

# Session config
SESSION_TTL=3600  # 1 hour (adjust based on usage)
MAX_MESSAGES_PER_SESSION=50  # Keep only last 50 messages
AUTO_SYNC_TO_DB=true  # Enable database sync
SYNC_INTERVAL=300  # Sync every 5 minutes
```

### Performance Tuning

**Low traffic (<100 users/day):**
```bash
SESSION_TTL=86400  # 24 hours
MAX_MESSAGES_PER_SESSION=100
```

**Medium traffic (100-1000 users/day):**
```bash
SESSION_TTL=3600  # 1 hour
MAX_MESSAGES_PER_SESSION=50
```

**High traffic (1000+ users/day):**
```bash
SESSION_TTL=1800  # 30 minutes
MAX_MESSAGES_PER_SESSION=20
```

## Security

### Production Checklist

- [ ] Enable Redis password: `REDIS_PASSWORD=strong_password`
- [ ] Use TLS for Redis connection in production
- [ ] Set up Redis access control (ACL)
- [ ] Enable conversation access control (verify user owns conversation)
- [ ] Implement rate limiting
- [ ] Encrypt sensitive conversations

### Enable Redis Auth

```bash
# Docker with password
docker run -d -p 6379:6379 \
  --name openta-redis \
  redis:alpine \
  redis-server --requirepass your_strong_password

# Update .env
REDIS_URL=redis://:your_strong_password@localhost:6379
```

## Resources

- **Architecture Guide:** [docs/ARCHITECTURE_CONVERSATION_HISTORY.md](./ARCHITECTURE_CONVERSATION_HISTORY.md)
- **API Migration:** [docs/API_MIGRATION_GUIDE.md](./API_MIGRATION_GUIDE.md)
- **Session Manager Code:** [app/services/session_manager.py](../app/services/session_manager.py)

## Summary

✅ **You're done!** Your agent now has:
- Fast conversation memory (Redis)
- Multi-turn context awareness
- Automatic session cleanup
- Production-ready architecture

**Test it:**
```bash
python examples/conversation_with_session.py
```

**Questions?** Check the [troubleshooting](#troubleshooting) section above!
