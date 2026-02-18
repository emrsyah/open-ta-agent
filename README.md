# Paper Research Platform - Minimal Setup

AI-powered paper research platform using FastAPI + DSPy + OpenRouter for Telkom University paper catalog.

## 📁 Project Structure

```
paper-research-platform/
├── backend/
│   ├── main.py           # FastAPI app (all-in-one)
│   └── requirements.txt  # Dependencies
├── frontend/
│   └── index.html        # Simple chat UI
└── README.md             # This file
```

**That's it! Just 3 files.** 🎉

---

## 🚀 Quick Start (5 minutes)

### 1. Clone/Setup

```bash
# Create project folder
mkdir paper-research-platform
cd paper-research-platform

# Copy the files (or create them manually)
# backend/main.py
# backend/requirements.txt
# frontend/index.html
```

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Set API Key

**Option A: OpenRouter (Recommended)**
```bash
# Get free API key at: https://openrouter.ai/settings/keys
export OPENROUTER_API_KEY="sk-or-your-key-here"
```

**Option B: OpenAI**
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

### 4. Run Backend

```bash
python main.py
```

**API will be available at:** `http://localhost:8000`

### 5. Test Frontend

Open `frontend/index.html` in your browser (or use Live Server extension).

---

## 🎯 Features

- ✅ **Search papers** - Basic keyword search
- ✅ **AI Chat** - RAG with papers as context
- ✅ **Streaming** - Real-time responses (like ChatGPT)
- ✅ **Citations** - Shows which papers were used
- ✅ **Multiple models** - Via OpenRouter (400+ models)

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /` | GET | API info |
| `GET /papers` | GET | List all papers |
| `GET /search` | GET | Search papers by keyword |
| `POST /chat` | POST | AI chat (streaming) |

### Example Requests

**Search Papers:**
```bash
curl "http://localhost:8000/search?query=machine+learning"
```

**AI Chat (Streaming):**
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "What papers discuss deep learning?", "stream": true}'
```

---

## 🔧 Configuration

All config is in `main.py` at the top:

```python
# Change these to customize:
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CHAT_MODEL = "openai/openai/gpt-4o-mini"  # or any OpenRouter model
```

### Popular Models

```python
# Cheap & fast
"openai/openai/gpt-4o-mini"
"openai/meta-llama/llama-3.3-70b-instruct"

# High quality
"openai/anthropic/claude-3.5-sonnet"
"openai/openai/gpt-4o"

# Free (for testing)
"openai/nvidia/llama-3.1-nemotron-70b-instruct:free"
```

---

## 📊 Replace Mock Data

Currently using 5 mock papers. Replace with your Telkom data:

```python
# In main.py, find PAPERS_DB and replace with your data:

PAPERS_DB = [
    Paper(
        id="your_id",
        title="Your Paper Title",
        authors=["Author 1", "Author 2"],
        abstract="Paper abstract here...",
        year=2024
    ),
    # ... more papers
]
```

Or load from file:
```python
import json

# Load from JSON
with open('papers.json') as f:
    papers_data = json.load(f)
    
PAPERS_DB = [Paper(**p) for p in papers_data]
```

---

## 🚀 Production Deployment

### Using Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/main.py .

EXPOSE 8000

CMD ["python", "main.py"]
```

Build & run:
```bash
docker build -t paper-research .
docker run -p 8000:8000 -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY paper-research
```

### Using Railway/Render/Fly.io

1. Push to GitHub
2. Connect to Railway/Render/Fly
3. Set environment variable: `OPENROUTER_API_KEY`
4. Deploy!

---

## 💰 Cost Estimation

Using OpenRouter:

| Usage | Model | Cost (per 100 queries) |
|-------|-------|----------------------|
| Basic chat | GPT-4o-mini | ~$0.04 |
| Deep research | Claude 3.5 | ~$0.45 |
| **Total** | Mixed | **~$0.50** |

**With free models for testing:** $0! 🎉

---

## 🛠️ Next Steps

1. ✅ **Add your paper data** - Replace `PAPERS_DB` with real data
2. ✅ **Improve retrieval** - Add vector search (see docs/FASTAPI_DSPY_IMPLEMENTATION.md)
3. ✅ **Add history** - Store conversations in Redis/DB
4. ✅ **Deep research** - Implement RLM module
5. ✅ **Authentication** - Add user accounts

---

## 🆘 Troubleshooting

### "OPENROUTER_API_KEY not set"
```bash
export OPENROUTER_API_KEY="sk-or-..."
```

### "Module not found"
```bash
pip install -r requirements.txt
```

### "CORS error"
Frontend URL not in allowed origins. Update `allow_origins` in `main.py`.

---

## 📚 Resources

- **OpenRouter**: https://openrouter.ai
- **DSPy Docs**: https://dspy.ai
- **FastAPI Docs**: https://fastapi.tiangolo.com

---

## 📝 License

MIT License - Feel free to use for your research!

---

**Questions?** The code is simple - just read `main.py`! 😊
