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

*At least one API key is required.

## 🧪 Testing

```bash
# Health check
curl http://localhost:8000/health

# Search papers
curl "http://localhost:8000/papers/search?query=machine+learning&limit=5"

# AI chat (non-streaming)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deep learning?", "stream": false}'

# AI chat (streaming)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deep learning?", "stream": true}'
```

## 📚 Architecture

### RAG Flow

```
User Question
     ↓
PaperRetriever (keyword search)
     ↓
RAG Module (DSPy + ChainOfThought)
     ↓
Streaming Response (SSE)
```

### Services

- **PaperRetriever**: Simple keyword-based search (replaceable with vector search)
- **RAGService**: DSPy module for question answering with citations
- **Streaming Utils**: SSE formatting for real-time responses

## 🔮 Future Improvements

1. **Vector Search**: Replace keyword search with `dspy.retrievers.Embeddings`
2. **Conversation History**: Add Redis/DB for multi-turn conversations
3. **RLM Agent**: Implement recursive language model for deep research
4. **Authentication**: Add JWT-based auth
5. **Rate Limiting**: Protect API endpoints

## 📖 Documentation

- See `docs/` for detailed implementation guides
- FastAPI docs: http://localhost:8000/docs (auto-generated)
- OpenAPI spec: http://localhost:8000/openapi.json
