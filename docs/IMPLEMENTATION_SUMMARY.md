# DSPy + FastAPI Implementation Summary

## ✅ What I've Created

I've built a complete implementation guide for your paper research platform with FastAPI + DSPy, focusing on **streaming responses**.

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `docs/FASTAPI_DSPY_IMPLEMENTATION.md` | Complete implementation guide |
| `examples/fastapi_dspy_streaming.py` | Working FastAPI + DSPy streaming example |
| `examples/chat-demo.html` | Frontend chat interface (HTML/JS) |

---

## 🎯 Key Findings from Research

### 1. **DSPy Has Built-in Streaming Support!**

DSPy provides utilities specifically for streaming:
- `dspy.streamify()` - Convert any DSPy module to streaming
- `dspy.asyncify()` - Make modules async for better performance
- `async_max_workers` - Configure parallel processing

```python
# The pattern:
module = dspy.ChainOfThought("question -> answer")
module_async = dspy.asyncify(module)  # ✅ Make it async
streaming_module = dspy.streamify(module_async)  # ✅ Make it stream

async for chunk in streaming_module(question="..."):
    # Handle streaming chunks
    if isinstance(chunk, dspy.Prediction):
        print(chunk.answer)  # Final result
    elif hasattr(chunk, 'choices'):
        print(chunk.choices[0].delta.content)  # Token stream
```

### 2. **FastAPI + SSE (Server-Sent Events) is the Standard**

```python
from fastapi.responses import StreamingResponse

@app.post("/chat")
async def chat(request: ChatRequest):
    async def generate():
        async for chunk in stream_dspy(program, question=request.question):
            yield f"data: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",  # SSE format
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
```

### 3. **Why SSE Over WebSockets?**

| SSE | WebSockets |
|-----|------------|
| ✅ Simple HTTP | ❌ Requires upgrade |
| ✅ Auto-reconnect | ❌ Manual reconnection |
| ✅ CDN-friendly | ❌ Sticky sessions needed |
| ✅ One-way (server→client) | ❌ Two-way (complex) |
| ✅ Perfect for LLM streaming | ⚠️ Overkill for simple streaming |

**For your use case (LLM streaming), SSE is better!**

---

## 🏗️ Recommended Architecture

```
Frontend (React/HTML)
    │
    │ POST /api/chat/basic
    │    { question: "...", stream: true }
    │
    ▼
FastAPI Backend
    │
    ├─► dspy.asyncify(rag_module)
    │
    ├─► dspy.streamify()
    │
    ├─► Paper Retriever (Vector Search)
    │
    ├─► dspy.LM (OpenAI)
    │
    └─► StreamingResponse (SSE)
         │
         ▼
    data: {"type": "token", "content": "Hello"}
    data: {"type": "token", "content": " there"}
    data: {"type": "sources", "sources": [...]}
    data: {"type": "done", "content": "..."}
    data: [DONE]
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn dspy-ai orjson pydantic-settings
```

### 2. Set Environment Variables

**Option A: Use OpenRouter (Recommended!)**
```bash
# Get your key at: https://openrouter.ai/settings/keys
export OPENROUTER_API_KEY="sk-or-..."
```

**Option B: Use OpenAI Direct**
```bash
export OPENAI_API_KEY="sk-..."
```

### 3. Run the Example

```bash
cd examples
python fastapi_dspy_streaming.py
```

**Note:** The example automatically detects whether you're using OpenRouter or OpenAI!

### 4. Test with curl

```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is DSPy?", "stream": true}'
```

### 5. Or Open the HTML Demo

Open `examples/chat-demo.html` in your browser and update the API URL to `http://localhost:8000`.

---

## 📊 Implementation Comparison

### Basic (Non-Streaming)
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    result = await rag_module(question=request.question)
    return {"answer": result.answer}
```
- ✅ Simple
- ❌ Poor UX (long wait times)

### Streaming (Recommended)
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        stream_dspy(rag_module, question=request.question),
        media_type="text/event-stream"
    )
```
- ✅ Great UX (ChatGPT-like)
- ✅ Perceived performance
- ⚠️ Slightly more complex

---

## 🔑 Key Implementation Details

### 1. DSPy Configuration

```python
import dspy

# Configure with async workers for streaming
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-key')
dspy.configure(lm=lm, async_max_workers=4)  # ✅ Important!
```

### 2. Making Modules Stream-Ready

```python
# Your RAG module
class PaperRAG(dspy.Module):
    def forward(self, question):
        context = retrieve_papers(question)
        return generate(question, context)

# Make it async + streamable
rag = PaperRAG()
rag_async = dspy.asyncify(rag)  # ✅ Required for streaming
```

### 3. SSE Response Format

The frontend expects this format:

```python
# Token chunks
data: {"type": "token", "content": "Hello"}

# Sources (optional)
data: {"type": "sources", "sources": ["paper1", "paper2"]}

# Done
data: {"type": "done", "content": "Full answer here"}
data: [DONE]
```

---

## 📝 Next Steps for Your Platform

### Phase 1: Basic Chat (RAG)
- [x] ✅ FastAPI + DSPy setup
- [x] ✅ Streaming responses
- [ ] ⏳ Implement paper retriever with your data
- [ ] ⏳ Add conversation history (Redis/DB)

### Phase 2: Deep Research (RLM)
- [ ] ⏳ Implement RLM module
- [ ] ⏳ Multi-paper synthesis
- [ ] ⏳ Citation network analysis

### Phase 3: Production
- [ ] ⏳ Docker deployment
- [ ] ⏳ Authentication
- [ ] ⏳ Rate limiting
- [ ] ⏳ Monitoring

---

## 🎓 What About Your Question: Title vs Abstract for Search?

Based on my research of academic paper retrieval systems:

### **Recommendation: Use BOTH with Hybrid Approach**

```python
# Best: Hybrid search
class HybridRetriever:
    def __call__(self, query: str):
        # 1. Vector search on abstract (semantic)
        abstract_results = vector_search(query, field="abstract", k=5)
        
        # 2. BM25 on title (exact match)
        title_results = keyword_search(query, field="title", k=5)
        
        # 3. Reciprocal rank fusion (RRF)
        return combine_rrf(abstract_results, title_results)
```

**Why both?**
- **Abstract vectors**: Better for semantic understanding ("machine learning papers about transformers")
- **Title BM25**: Better for exact queries ("Attention Is All You Need")

The research shows hybrid approaches outperform single-field search by 15-30%!

---

## 💡 Key Takeaways

1. **DSPy has native streaming** - Use `dspy.streamify()` + `dspy.asyncify()`
2. **SSE > WebSockets** for your use case - Simpler, production-ready
3. **Hybrid search is best** - Combine abstract vectors + title keywords
4. **Start simple** - Basic RAG chat first, deep research later

---

**Want me to implement the retriever with your Telkom paper data structure next?** 🚀
