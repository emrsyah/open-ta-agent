# Telkom Paper Research API - Backend

FastAPI + DSPy backend for AI-powered paper research platform.

## 📁 Project Structure

```
backend/
├── app/
│   ├── __init__.py              # Package init
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings & configuration
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py          # AI chat endpoints
│   │       ├── papers.py        # Paper search endpoints
│   │       └── health.py        # Health check endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py            # Pydantic schemas
│   │   └── exceptions.py        # Custom exceptions
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rag.py               # RAG service with DSPy
│   │   └── retriever.py         # Paper retriever
│   └── utils/
│       ├── __init__.py
│       └── streaming.py         # SSE streaming utilities
├── data/
│   └── papers.json              # Paper data (optional)
├── .env                         # Environment variables
├── .env.example                 # Environment template
├── requirements.txt             # Dependencies
└── run.py                       # Convenience runner
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Run the Server

```bash
# Activate virtual environment
.venv\Scripts\activate

# Option 1: Using run.py
python run.py

# Option 2: Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Option 3: Using main.py
python -m app.main
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info & available endpoints |
| `/health` | GET | Health check |
| `/papers/search` | GET/POST | Search papers by keyword |
| `/papers/list` | GET | List all papers |
| `/chat/basic` | POST | AI chat (streaming or sync) |
| `/chat/deep` | POST | Deep research (RLM) - TBD |

## 🔧 Configuration

All configuration is done via environment variables (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes* | OpenRouter API key |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (alternative) |
| `DSPY_MODEL` | No | Model to use (default: Gemini Pro) |
| `DSPY_MAX_WORKERS` | No | Async workers (default: 4) |
| `RETRIEVAL_TOP_K` | No | Papers per query (default: 3) |
| `REDIS_URL` | No** | Redis URL for session management |
| `SESSION_TTL` | No | Session timeout (default: 3600s) |
| `DATABASE_URL` | No | PostgreSQL/Supabase for long-term storage |

*At least one API key is required.  
**Required for conversation history feature.

## 🧪 Testing

### New API Structure (Recommended)

```bash
# Health check
curl http://localhost:8000/health

# Search papers
curl "http://localhost:8000/papers/search?query=machine+learning&limit=5"

# AI chat with new meta_params structure
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is deep learning?",
    "meta_params": {
      "stream": false,
      "language": "id-ID",
      "source_preference": "all"
    }
  }'

# Streaming with conversation history
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tell me more about that",
    "meta_params": {
      "stream": true,
      "conversation_id": "conv_abc123"
    }
  }'
```

### Backwards Compatible (Old Format Still Works)

```bash
# Old format still supported
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deep learning?", "stream": false}'
```

## 📚 Architecture

### RAG Flow

```
User Question + Conversation History
     ↓
Intent Classification (research vs general)
     ↓
Query Generation (LLM-optimized search keywords)
     ↓
PaperRetriever (vector/keyword search)
     ↓
RAG Module (DSPy + ChainOfThought + History)
     ↓
Streaming Response (SSE) or JSON
```

### Services

- **PaperRetriever**: Simple keyword-based search (replaceable with vector search)
- **RAGService**: DSPy module for question answering with citations
- **Streaming Utils**: SSE formatting for real-time responses

## 🆕 New API Structure

We've upgraded to a cleaner API structure with `meta_params`:

```json
{
  "query": "What is machine learning?",
  "meta_params": {
    "mode": "basic",
    "stream": true,
    "language": "id-ID",
    "timezone": "Asia/Jakarta",
    "source_preference": "all",
    "conversation_id": "conv_123",
    "is_incognito": false,
    "attachments": []
  }
}
```

### New Features:
- 🌍 **Multilingual**: Respond in Indonesian, English, etc.
- 📚 **Source Filtering**: Papers only, general knowledge, or all
- 🕵️ **Incognito Mode**: Private queries (no history saved)
- 🌐 **Timezone Aware**: Context-aware timestamps
- 📎 **Attachments**: File upload support (coming soon)

**Migration:** See [`docs/API_MIGRATION_GUIDE.md`](docs/API_MIGRATION_GUIDE.md)

## 💬 Conversation History & Session Management

The agent supports multi-turn conversations with Redis-based session management!

### Quick Start:

```bash
# 1. Start Redis (required for conversation history)
docker run -d -p 6379:6379 redis:alpine

# 2. First message (creates new conversation)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What papers discuss transformers?",
    "meta_params": {"stream": false}
  }'

# 3. Follow-up (agent remembers context via Redis)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Which one is most recent?",
    "meta_params": {
      "stream": false,
      "conversation_id": "conv_abc123"
    }
  }'
```

### Architecture:

**Hybrid Redis + Database** (recommended for production)
- 🚀 Redis: Fast access (<5ms) for active conversations
- 💾 Database: Long-term storage and analytics
- 🧹 Auto-cleanup: TTL-based session expiry
- 📊 Scalable: Handles 10k+ concurrent users

### Features:

- ✅ Context-aware responses using `dspy.History`
- ✅ Redis-based session management (fast!)
- ✅ Optional database sync for durability
- ✅ Automatic history pruning
- ✅ Cross-device conversation continuity
- ✅ Incognito mode for privacy

### Resources:

- **[Architecture Guide](docs/ARCHITECTURE_CONVERSATION_HISTORY.md)** ⭐ Start here!
- **[API Migration Guide](docs/API_MIGRATION_GUIDE.md)** - Update your code
- **[Session Manager](app/services/session_manager.py)** - Implementation
- **[Examples](examples/conversation_with_session.py)** - Interactive demos

## 🔮 Future Improvements

1. **Vector Search**: Replace keyword search with `dspy.retrievers.Embeddings`
2. **Session Persistence**: Add Redis/DB for persistent conversation storage
3. **RLM Agent**: Implement recursive language model for deep research
4. **Authentication**: Add JWT-based auth
5. **Rate Limiting**: Protect API endpoints
6. **History Summarization**: Auto-summarize long conversations

## 📖 Documentation

- See `docs/` for detailed implementation guides
- FastAPI docs: http://localhost:8000/docs (auto-generated)
- OpenAPI spec: http://localhost:8000/openapi.json
