# OpenRouter vs OpenAI: Quick Comparison

## 🎯 TL;DR

**Use OpenRouter** - It's cheaper, more flexible, and works perfectly with DSPy!

---

## 💰 Cost Comparison

| Model | Via OpenRouter | Via OpenAI Direct | Savings |
|-------|---------------|-------------------|---------|
| **GPT-4o-mini** | $0.15/1M in, $0.60/1M out | Same | Same |
| **Claude 3.5 Sonnet** | $3/1M in, $15/1M out | $3/1M in, $15/1M out | Same |
| **Llama 3.3 70B** | $0.10/1M tokens | N/A | ✅ Open source! |
| **NVIDIA Nemotron** | **FREE** | N/A | ✅ 100% savings! |
| **Mistral NeMo** | $0.15/1M tokens | N/A | ✅ Cheaper than GPT-4 |

---

## ✅ Advantages of OpenRouter

### 1. **Single API Key**
```bash
# Before: Managing multiple keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
GOOGLE_API_KEY=...

# Now: Just one!
OPENROUTER_API_KEY=sk-or-...
```

### 2. **Access to 400+ Models**
- OpenAI (GPT-4, GPT-4o, etc.)
- Anthropic (Claude 3.5 Sonnet, etc.)
- Google (Gemini 2.5 Pro)
- Meta (Llama 3.x)
- Mistral (NeMo, Mixtral)
- And 100+ more!

### 3. **Automatic Fallbacks**
```python
# If Claude is down, automatically try GPT-4
lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
             extra_body={
                 "models": [
                     "anthropic/claude-3.5-sonnet",
                     "openai/gpt-4o",  # Fallback
                     "google/gemini-2.5-pro"  # Fallback 2
                 ]
             })
```

### 4. **Free Models for Development**
```python
# Perfect for testing!
lm = dspy.LM('openai/nvidia/llama-3.1-nemotron-70b-instruct:free',
             api_base='https://openrouter.ai/api/v1',
             api_key='sk-or-...')
```

### 5. **Real-Time Cost Tracking**
- Visit https://openrouter.ai/activity
- See costs per model
- Monitor usage in real-time
- Set spending limits

### 6. **Provider Routing**
```python
# Optimize for cost, speed, or quality
lm = dspy.LM('openai/openrouter/auto',
             extra_body={
                 "provider": {
                     "order": ["nvidia", "huggingface"],  # Free first!
                     "allow_fallbacks": True
                 }
             })
```

---

## ⚖️ When to Use What?

### Use OpenRouter When:
- ✅ You want access to multiple models
- ✅ You want automatic fallbacks
- ✅ You want to minimize cost
- ✅ You're building a production app
- ✅ You need flexibility in model selection

### Use OpenAI Direct When:
- ⚠️ You only need GPT models
- ⚠️ You have enterprise pricing with OpenAI
- ⚠️ You need specific OpenAI features not available elsewhere

---

## 🔧 DSPy Configuration Comparison

### With OpenAI Direct
```python
import os
import dspy

lm = dspy.LM(
    'openai/gpt-4o-mini',
    api_key=os.getenv("OPENAI_API_KEY")
)
dspy.configure(lm=lm)
```

### With OpenRouter (Recommended)
```python
import os
import dspy

lm = dspy.LM(
    'openai/openai/gpt-4o-mini',  # Note: openai/ prefix
    api_base='https://openrouter.ai/api/v1',
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model_type='chat'
)
dspy.configure(lm=lm)
```

**Only 2 lines of difference!** 

---

## 📊 Real-World Example: Your Paper Research Platform

### Option A: OpenAI Direct
```python
# Basic chat: GPT-4o-mini
chat_lm = dspy.LM('openai/gpt-4o-mini', 
                   api_key=OPENAI_KEY)

# Deep research: GPT-4o (expensive!)
research_lm = dspy.LM('openai/gpt-4o',
                       api_key=OPENAI_KEY)

# Cost per 100 queries (avg 500 tokens each):
# - Basic chat: ~$0.04
# - Deep research: ~$0.75
# Total: ~$0.79 per 100 queries
```

### Option B: OpenRouter (Better!)
```python
# Basic chat: GPT-4o-mini (same price)
chat_lm = dspy.LM('openai/openai/gpt-4o-mini',
                   api_base='https://openrouter.ai/api/v1',
                   api_key=OPENROUTER_KEY)

# Deep research: Claude 3.5 Sonnet (better quality!)
research_lm = dspy.LM('openai/anthropic/claude-3.5-sonnet',
                       api_base='https://openrouter.ai/api/v1',
                       api_key=OPENROUTER_KEY,
                       model_type='chat')

# Cost per 100 queries (avg 500 tokens each):
# - Basic chat: ~$0.04 (same)
# - Deep research: ~$0.45 (better model, similar cost!)
# Total: ~$0.49 per 100 queries
# 💰 38% savings + better quality!
```

### Option C: OpenRouter (Budget-Friendly)
```python
# Basic chat: Llama 3.3 70B (open source!)
chat_lm = dspy.LM('openai/meta-llama/llama-3.3-70b-instruct',
                   api_base='https://openrouter.ai/api/v1',
                   api_key=OPENROUTER_KEY)

# Deep research: Mistral NeMo (great value!)
research_lm = dspy.LM('openai/mistralai/mistral-nemo',
                       api_base='https://openrouter.ai/api/v1',
                       api_key=OPENROUTER_KEY)

# Cost per 100 queries (avg 500 tokens each):
# - Basic chat: ~$0.01
# - Deep research: ~$0.02
# Total: ~$0.03 per 100 queries
# 💰 96% savings!
```

---

## 🎓 My Recommendation

**For your Telkom Paper Research Platform:**

### Development Phase
```python
# Use FREE models for testing
lm = dspy.LM(
    'openai/nvidia/llama-3.1-nemotron-70b-instruct:free',
    api_base='https://openrouter.ai/api/v1',
    api_key=OPENROUTER_KEY
)
```

### Production (Cost-Optimized)
```python
# Basic Chat: Llama 3.3 (excellent, cheap)
CHAT_MODEL = 'openai/meta-llama/llama-3.3-70b-instruct'

# Deep Research: Claude 3.5 (best for research)
RESEARCH_MODEL = 'openai/anthropic/claude-3.5-sonnet'
```

### Production (Balanced)
```python
# Basic Chat: GPT-4o-mini (fast, cheap)
CHAT_MODEL = 'openai/openai/gpt-4o-mini'

# Deep Research: GPT-4o or Claude 3.5
RESEARCH_MODEL = 'openai/openai/gpt-4o'
```

---

## ✅ Migration Checklist

- [ ] Sign up at https://openrouter.ai
- [ ] Get API key from https://openrouter.ai/settings/keys
- [ ] Add `OPENROUTER_API_KEY=sk-or-...` to `.env`
- [ ] Update config: Add `api_base='https://openrouter.ai/api/v1'`
- [ ] Update model names: Add `openai/` prefix
- [ ] Test with free model first
- [ ] Monitor costs at https://openrouter.ai/activity
- [ ] Deploy! 🚀

---

## 🎉 Summary

**OpenRouter is a no-brainer for your project:**

1. ✅ **Works perfectly with DSPy** (OpenAI-compatible)
2. ✅ **Single API key** for 400+ models
3. ✅ **Automatic fallbacks** (better reliability)
4. ✅ **Free models** for development
5. ✅ **Cost tracking** built-in
6. ✅ **Same code** - just change API URL
7. ✅ **Better models** available (Claude, Gemini, etc.)

**Configuration change is minimal:**
```python
# Before
lm = dspy.LM('openai/gpt-4o-mini', api_key='...')

# After
lm = dspy.LM('openai/openai/gpt-4o-mini',
             api_base='https://openrouter.ai/api/v1',
             api_key='sk-or-...')
```

**That's it! Everything else stays the same.** 🎉
