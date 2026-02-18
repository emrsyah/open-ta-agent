# Using OpenRouter with DSPy - Complete Guide

## ✅ Yes! OpenRouter Works Perfectly with DSPy

OpenRouter provides an **OpenAI-compatible API**, which DSPy fully supports. This gives you access to 400+ models through a single API key!

---

## 🚀 Quick Setup

### 1. Get OpenRouter API Key

```bash
# Visit: https://openrouter.ai/settings/keys
# Copy your API key (starts with sk-or-...)
export OPENROUTER_API_KEY="sk-or-..."
```

### 2. Configure DSPy with OpenRouter

```python
import dspy

# Option A: Using OpenRouter with any model
lm = dspy.LM(
    'openai/openai/gpt-4o-mini',  # Note: openai/ prefix + provider/model
    api_base='https://openrouter.ai/api/v1',
    api_key='your-openrouter-key'
)
dspy.configure(lm=lm)

# Option B: Using OpenRouter's auto model selection
lm = dspy.LM(
    'openai/openrouter/auto',  # Let OpenRouter choose the best model
    api_base='https://openrouter.ai/api/v1',
    api_key='your-openrouter-key'
)
dspy.configure(lm=lm)

# Option C: Direct model specification
lm = dspy.LM(
    'openai/anthropic/claude-3.5-sonnet',  # Specific model
    api_base='https://openrouter.ai/api/v1',
    api_key='your-openrouter-key',
    model_type='chat'
)
dspy.configure(lm=lm)
```

---

## 📋 Popular OpenRouter Models

Here are some great options for your paper research platform:

### For Cost-Effective (Basic Chat)
```python
# GPT-4o-mini (cheap, fast)
lm = dspy.LM('openai/openai/gpt-4o-mini', 
             api_base='https://openrouter.ai/api/v1',
             api_key='key')

# Llama 3.3 70B (open source, good quality)
lm = dspy.LM('openai/meta-llama/llama-3.3-70b-instruct',
             api_base='https://openrouter.ai/api/v1',
             api_key='key')

# Mistral NeMo (great reasoning)
lm = dspy.LM('openai/mistralai/mistral-nemo',
             api_base='https://openrouter.ai/api/v1',
             api_key='key')
```

### For High Quality (Deep Research)
```python
# Claude 3.5 Sonnet (excellent for research)
lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
             api_base='https://openrouter.ai/api/v1',
             api_key='key',
             model_type='chat')

# GPT-4o (balanced)
lm = dspy.LM('openai/openai/gpt-4o',
             api_base='https://openrouter.ai/api/v1',
             api_key='key')

# Gemini 2.5 Pro (Google's latest)
lm = dspy.LM('openai/google/gemini-2.5-pro-preview-03-25',
             api_base='https://openrouter.ai/api/v1',
             api_key='key')
```

### For Budget (Free Options!)
```python
# Free models available on OpenRouter
lm = dspy.LM('openai/nvidia/llama-3.1-nemotron-70b-instruct:free',
             api_base='https://openrouter.ai/api/v1',
             api_key='key')

# Or use auto-routing with provider preferences
lm = dspy.LM('openai/openrouter/auto',
             api_base='https://openrouter.ai/api/v1',
             api_key='key',
             extra_body={
                 "provider": {
                     "order": ["nvidia", "huggingface"],  # Try free providers first
                     "allow_fallbacks": True
                 }
             })
```

---

## 🔧 Complete Implementation with OpenRouter

### Updated Configuration

```python
# app/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # OpenRouter Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Model Selection
    CHAT_MODEL: str = "openai/openai/gpt-4o-mini"  # Basic chat
    RESEARCH_MODEL: str = "openai/anthropic/claude-3.5-sonnet"  # Deep research
    EMBEDDING_MODEL: str = "openai/openai/text-embedding-3-small"
    
    # DSPy Config
    DSPY_MAX_WORKERS: int = 4
    
    # Your App Name (for OpenRouter rankings)
    APP_NAME: str = "Telkom Paper Research"
    APP_URL: str = "https://your-app.com"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### Updated Main App

```python
# app/main.py
import dspy
from fastapi import FastAPI
from app.config import settings

app = FastAPI(title=settings.APP_NAME)

@app.on_event("startup")
async def startup_event():
    """Configure DSPy with OpenRouter"""
    
    # Primary LM for chat
    chat_lm = dspy.LM(
        settings.CHAT_MODEL,
        api_base=settings.OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
        model_type="chat",
        # Optional: Add headers for OpenRouter rankings
        extra_headers={
            "HTTP-Referer": settings.APP_URL,
            "X-Title": settings.APP_NAME,
        }
    )
    
    # Secondary LM for deep research (if different)
    if settings.RESEARCH_MODEL != settings.CHAT_MODEL:
        research_lm = dspy.LM(
            settings.RESEARCH_MODEL,
            api_base=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            model_type="chat",
            extra_headers={
                "HTTP-Referer": settings.APP_URL,
                "X-Title": settings.APP_NAME,
            }
        )
    else:
        research_lm = chat_lm
    
    # Configure DSPy
    dspy.configure(
        lm=chat_lm,
        async_max_workers=settings.DSPY_MAX_WORKERS
    )
    
    # Store LMs in app state for later use
    app.state.chat_lm = chat_lm
    app.state.research_lm = research_lm
    
    print(f"✅ DSPy configured with OpenRouter")
    print(f"   Chat model: {settings.CHAT_MODEL}")
    print(f"   Research model: {settings.RESEARCH_MODEL}")
```

### Updated Chat Endpoint

```python
# app/api/routes/chat.py
from fastapi import APIRouter, Request
from app.dspy_modules.rag import BasicPaperChat

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/basic")
async def chat_basic(request: Request, question: str, stream: bool = True):
    """Basic AI chat with OpenRouter + DSPy + Streaming"""
    
    # Get LM from app state
    chat_lm = request.app.state.chat_lm
    
    # Initialize RAG with chat LM
    rag_module = BasicPaperChat(retriever=retriever)
    rag_module.set_lm(chat_lm)
    rag_module_async = dspy.asyncify(rag_module)
    
    if stream:
        # Stream response
        return await stream_dspy_prediction(
            rag_module_async,
            question=question
        )
    else:
        # Non-streaming
        result = await rag_module_async(question=question)
        return {"answer": result.answer, "sources": result.sources}

@router.post("/deep")
async def chat_deep(request: Request, question: str, stream: bool = True):
    """Deep research with better model"""
    
    # Get research LM (higher quality)
    research_lm = request.app.state.research_lm
    
    # Initialize deep research module
    deep_module = DeepResearch(retriever=retriever)
    deep_module.set_lm(research_lm)
    deep_module_async = dspy.asyncify(deep_module)
    
    if stream:
        return await stream_dspy_prediction(
            deep_module_async,
            question=question
        )
    else:
        result = await deep_module_async(question=question)
        return {"answer": result.answer, "sources": result.sources}
```

---

## 💰 Cost Comparison

OpenRouter shows real-time pricing. Here's what you might pay:

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Best For |
|-------|---------------------|----------------------|----------|
| **GPT-4o-mini** | $0.15 | $0.60 | Basic chat, cost-effective |
| **Llama 3.3 70B** | $0.10 | $0.10 | Budget option |
| **Claude 3.5 Sonnet** | $3.00 | $15.00 | Deep research |
| **GPT-4o** | $2.50 | $10.00 | Balanced |
| **Mistral NeMo** | $0.15 | $0.15 | Fast, good quality |
| **NVIDIA Nemotron** | **FREE** | **FREE** | Testing/Development |

---

## 🎯 Recommended Setup for Your Platform

### Development
```python
# Use free models for testing
lm = dspy.LM(
    'openai/nvidia/llama-3.1-nemotron-70b-instruct:free',
    api_base='https://openrouter.ai/api/v1',
    api_key=os.getenv("OPENROUTER_API_KEY")
)
```

### Production (Basic Chat)
```python
# Cost-effective but good quality
lm = dspy.LM(
    'openai/openai/gpt-4o-mini',  # ~$0.75 per 1M tokens
    api_base='https://openrouter.ai/api/v1',
    api_key=os.getenv("OPENROUTER_API_KEY")
)
```

### Production (Deep Research)
```python
# Best quality for research analysis
lm = dspy.LM(
    'openai/anthropic/claude-3.5-sonnet',  # ~$9 per 1M tokens
    api_base='https://openrouter.ai/api/v1',
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model_type='chat'
)
```

---

## 🔑 Key Benefits of Using OpenRouter

### 1. **Single API Key**
```bash
# Before: Multiple keys
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GOOGLE_API_KEY="..."

# Now: Just one!
export OPENROUTER_API_KEY="sk-or-..."
```

### 2. **Easy Model Switching**
```python
# Change models without code changes
lm = dspy.LM('openai/openrouter/auto', ...)  # Let OpenRouter choose

# Or specify provider preferences
lm = dspy.LM('openai/openrouter/auto',
             extra_body={
                 "provider": {
                     "order": ["anthropic", "openai"],  # Try Claude first
                     "allow_fallbacks": True
                 }
             })
```

### 3. **Automatic Fallbacks**
```python
# If primary model fails, try backup
lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
             extra_body={
                 "models": [
                     "anthropic/claude-3.5-sonnet",  # Primary
                     "openai/gpt-4o",                 # Fallback 1
                     "google/gemini-2.5-pro"          # Fallback 2
                 ]
             })
```

### 4. **Streaming Support** ✅
OpenRouter fully supports streaming, which we need for your chat interface!

```python
# Works perfectly with dspy.streamify()
streaming_module = dspy.streamify(rag_module)
async for chunk in streaming_module(question="..."):
    # Stream tokens in real-time
    print(chunk)
```

---

## 📊 Complete Example: OpenRouter + DSPy + FastAPI

```python
import dspy
import os
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

# Configure with OpenRouter
lm = dspy.LM(
    'openai/openai/gpt-4o-mini',
    api_base='https://openrouter.ai/api/v1',
    api_key=os.getenv('OPENROUTER_API_KEY'),
    model_type='chat'
)
dspy.configure(lm=lm, async_max_workers=4)

# Create RAG module
class PaperRAG(dspy.Module):
    def __init__(self, retriever):
        super().__init__()
        self.retriever = retriever
        self.generate = dspy.ChainOfThought("question, context -> answer")
    
    def forward(self, question):
        context = self.retriever(question)
        return self.generate(question=question, context=context)

# Use it
rag = PaperRAG(retriever=your_retriever)
rag_async = dspy.asyncify(rag)

@app.post("/chat")
async def chat(question: str):
    async def generate():
        streaming_module = dspy.streamify(rag_async)
        
        async for value in streaming_module(question=question):
            if isinstance(value, dspy.Prediction):
                yield f"data: {value.answer}\n\n"
            elif hasattr(value, 'choices'):
                chunk = value.choices[0].delta.content or ""
                yield f"data: {chunk}\n\n"
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## ⚡ Performance Tips

### 1. Use Different Models for Different Tasks
```python
# Fast model for retrieval query generation
fast_lm = dspy.LM('openai/meta-llama/llama-3.1-8b-instruct',
                  api_base='https://openrouter.ai/api/v1',
                  api_key=key)

# Smart model for answer generation
smart_lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
                   api_base='https://openrouter.ai/api/v1',
                   api_key=key)
```

### 2. Configure Token Limits
```python
# For short answers
lm = dspy.LM('openai/openai/gpt-4o-mini',
             api_base='https://openrouter.ai/api/v1',
             api_key=key,
             max_tokens=500)  # Shorter responses

# For deep analysis
lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
             api_base='https://openrouter.ai/api/v1',
             api_key=key,
             max_tokens=4000)  # Longer responses
```

### 3. Monitor Costs
OpenRouter provides real-time cost tracking:
- Visit https://openrouter.ai/activity
- See costs per model
- Monitor usage patterns

---

## ✅ Migration Checklist

- [ ] Get OpenRouter API key
- [ ] Update `.env` with `OPENROUTER_API_KEY`
- [ ] Update `config.py` with OpenRouter base URL
- [ ] Update model names (add `openai/` prefix)
- [ ] Test with free model first
- [ ] Update production models
- [ ] Monitor costs on OpenRouter dashboard

---

## 🎉 Summary

**Yes, you can absolutely use OpenRouter instead of OpenAI!**

### Key Points:
1. ✅ **OpenAI-compatible** - Works seamlessly with DSPy
2. ✅ **Streaming support** - Perfect for your chat interface
3. ✅ **400+ models** - Access to GPT-4, Claude, Gemini, Llama, etc.
4. ✅ **Single API key** - Simplifies credential management
5. ✅ **Automatic fallbacks** - Better reliability
6. ✅ **Cost tracking** - Real-time monitoring
7. ✅ **Free options** - Great for development

### Configuration Pattern:
```python
lm = dspy.LM(
    'openai/PROVIDER/MODEL',  # e.g., openai/anthropic/claude-3.5-sonnet
    api_base='https://openrouter.ai/api/v1',
    api_key='sk-or-...'
)
dspy.configure(lm=lm)
```

---

**Ready to implement?** The code changes are minimal - just update the API base URL and add the `openai/` prefix to model names! 🚀
