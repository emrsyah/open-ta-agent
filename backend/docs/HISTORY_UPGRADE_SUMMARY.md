# History Management Upgrade Summary

## Overview

Successfully upgraded the OpenTA Agent backend to support **conversation history management** using DSPy's `dspy.History` utility. This enables context-aware, multi-turn conversations where the agent can reference previous questions and answers.

## Changes Made

### 1. Core Models (`app/core/models.py`)

#### Added: `ConversationMessage` Model
```python
class ConversationMessage(BaseModel):
    """Single message in conversation history."""
    question: str
    answer: str
    sources: Optional[List[str]]
    context: Optional[str]
```

#### Updated: `ChatRequest` Model
- Added `history` field to accept conversation history
- Type: `Optional[List[ConversationMessage]]`
- Backwards compatible (history is optional)

**Before:**
```python
class ChatRequest(BaseModel):
    question: str
    stream: bool = True
    session_id: Optional[str] = None
```

**After:**
```python
class ChatRequest(BaseModel):
    question: str
    stream: bool = True
    session_id: Optional[str] = None
    history: Optional[List[ConversationMessage]] = None
```

### 2. RAG Service (`app/services/rag.py`)

#### Updated: `PaperChatSignature`
- Added `history: dspy.History` as input field
- Updated docstring to explain history-aware behavior

**Before:**
```python
class PaperChatSignature(dspy.Signature):
    question: str = dspy.InputField()
    context: str = dspy.InputField()
    answer: str = dspy.OutputField()
    sources: List[str] = dspy.OutputField()
```

**After:**
```python
class PaperChatSignature(dspy.Signature):
    question: str = dspy.InputField()
    context: str = dspy.InputField()
    history: dspy.History = dspy.InputField()  # ← NEW
    answer: str = dspy.OutputField()
    sources: List[str] = dspy.OutputField()
```

#### Updated: `PaperRAG.forward()`
- Now accepts `history` parameter
- Defaults to empty history if none provided
- Passes history to the generate module

#### Added: `RAGService._convert_to_dspy_history()`
New helper method that converts API history format to DSPy format:

```python
def _convert_to_dspy_history(self, history_messages: Optional[List[dict]]) -> dspy.History:
    """Convert conversation history from request model to dspy.History"""
    if not history_messages:
        return dspy.History(messages=[])
    
    dspy_messages = []
    for msg in history_messages:
        history_entry = {
            "question": msg.get("question", ""),
            "answer": msg.get("answer", ""),
            "context": msg.get("context", ""),
        }
        if msg.get("sources"):
            history_entry["sources"] = msg.get("sources")
        dspy_messages.append(history_entry)
    
    return dspy.History(messages=dspy_messages)
```

#### Updated: `RAGService.chat()`
- Now accepts `history` parameter
- Converts and passes history to RAG module
- Logs history usage for debugging

### 3. Chat Routes (`app/api/routes/chat.py`)

#### Updated: Non-Streaming Response
```python
# Convert history to dict format and pass to service
history = [msg.model_dump() for msg in request.history] if request.history else None
result = await rag_service.chat(request.question, history=history)
```

#### Updated: Streaming Response
```python
# Convert history to dspy.History and pass to streaming function
history_messages = [msg.model_dump() for msg in request.history] if request.history else None
dspy_history = rag_service._convert_to_dspy_history(history_messages)

return StreamingResponse(
    stream_dspy_response(
        rag_module, 
        retriever, 
        question=request.question,
        history=dspy_history,  # ← NEW
        ...
    )
)
```

### 4. Streaming Utilities (`app/utils/streaming.py`)

#### Updated: `stream_dspy_response()`
- Added `history` parameter
- Passes history to the DSPy program during streaming
- Defaults to empty history if none provided

**Signature Change:**
```python
async def stream_dspy_response(
    dspy_program: Any,
    retriever: Any,
    question: str,
    query_generator: Any = None,
    intent_classifier: Any = None,
    cheap_lm: Any = None,
    history: Any = None  # ← NEW
) -> AsyncGenerator[str, None]:
```

## New Files Created

### 1. Documentation
**`docs/CONVERSATION_HISTORY.md`** (8KB+)
- Complete guide to conversation history feature
- Architecture explanation
- Usage examples (Python, cURL, React)
- Best practices and troubleshooting
- Performance considerations

### 2. Examples
**`examples/chat_with_history.py`**
- Interactive demo script
- 5 different demo scenarios:
  1. Basic multi-turn conversation
  2. Streaming with history
  3. Research session
  4. Mixed general + research
  5. History management

**Usage:**
```bash
python examples/chat_with_history.py
```

### 3. Tests
**`tests/test_history.py`**
- Unit tests for history conversion
- Tests for API models
- Tests for RAG module integration
- History pruning helpers

**Run tests:**
```bash
pytest tests/test_history.py -v
```

### 4. Updated Documentation
**`README.md`**
- Added conversation history section
- Updated RAG flow diagram
- Added links to new documentation

## How It Works

### Data Flow

```
1. Client sends ChatRequest with history
   ↓
2. FastAPI route extracts history from request
   ↓
3. RAGService._convert_to_dspy_history() converts format
   ↓
4. dspy.History object created
   ↓
5. Passed to PaperRAG.forward() along with question & context
   ↓
6. DSPy includes history in prompt to LLM
   ↓
7. LLM generates context-aware response
   ↓
8. Response sent back to client
```

### Example Prompt (Internal)

When history is provided, DSPy automatically formats it:

```
System message:
You are 'OpenTA Agent', a specialized research assistant...

User message (Turn 1):
[[ ## question ## ]]
What is machine learning?

[[ ## context ## ]]
[Paper abstracts...]

[[ ## history ## ]]

Assistant message (Turn 1):
[[ ## answer ## ]]
Machine learning is a subset of AI that enables systems to learn from data...

[[ ## sources ## ]]
["Paper_001", "Paper_002"]

User message (Turn 2):
[[ ## question ## ]]
What are its main applications?

[[ ## context ## ]]
[Paper abstracts...]

[[ ## history ## ]]
{"messages": [{"question": "What is machine learning?", "answer": "Machine learning is...", "sources": ["Paper_001", "Paper_002"]}]}

Respond with the corresponding output fields...
```

## API Usage Examples

### Without History (Backwards Compatible)
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?", "stream": false}'
```

### With History (New Feature)
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Tell me more about that",
    "stream": false,
    "history": [
      {
        "question": "What is AI?",
        "answer": "Artificial Intelligence is...",
        "sources": ["Paper_123"]
      }
    ]
  }'
```

### Python Client Example
```python
import requests

history = []

def chat(question):
    response = requests.post(
        "http://localhost:8000/chat/basic",
        json={
            "question": question,
            "stream": False,
            "history": history
        }
    )
    result = response.json()
    
    # Add to history for next question
    history.append({
        "question": question,
        "answer": result["answer"],
        "sources": result.get("sources", [])
    })
    
    return result

# Multi-turn conversation
chat("What is deep learning?")
chat("What are its applications?")  # Knows context from previous turn
chat("Which paper covers CNNs?")    # Remembers entire conversation
```

## Benefits

### 1. Context Awareness
- Agent can understand follow-up questions with pronouns ("it", "that", "those")
- No need to repeat context in every question

### 2. Better User Experience
- Natural, conversational flow
- Agent can reference previous answers
- Coherent multi-turn research sessions

### 3. Research Efficiency
- Build incrementally on previous answers
- Dive deeper into topics without repeating context
- Compare and contrast papers mentioned earlier

### 4. Flexibility
- Works with both streaming and non-streaming modes
- Optional - backwards compatible with existing clients
- Session management via `session_id`

## Testing

Run the comprehensive test suite:

```bash
# Unit tests
pytest tests/test_history.py -v

# Integration tests (requires running server)
python examples/chat_with_history.py
```

Manual testing:
```bash
# Start server
python run.py

# Test without history
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?", "stream": false}'

# Test with history
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Tell me more",
    "stream": false,
    "history": [{"question": "What is AI?", "answer": "AI is artificial intelligence"}]
  }'
```

## Performance Considerations

### Token Usage
Each history turn adds tokens to the prompt. Recommended limits:
- **Good:** 5-10 recent turns (~2-5K tokens)
- **Warning:** 20+ turns (~10K+ tokens)
- **Bad:** Unlimited history (may exceed context window)

### Best Practices
1. Limit history to recent turns (implement pruning)
2. Clear history when changing topics
3. Use `session_id` to track different conversations
4. Consider caching for frequently accessed sessions

### History Pruning Example
```python
def prune_history(history, max_turns=10):
    """Keep only the most recent turns"""
    if len(history) > max_turns:
        return history[-max_turns:]
    return history
```

## Backwards Compatibility

✅ **Fully backwards compatible!**

- History field is optional
- Existing clients work without changes
- No breaking changes to API
- Default behavior unchanged when history is not provided

## Migration Guide

### For Existing Clients

No changes required! Your existing code continues to work.

### To Enable History

1. **Track conversation history in your client:**
```python
history = []
```

2. **After each response, append to history:**
```python
history.append({
    "question": user_question,
    "answer": response["answer"],
    "sources": response.get("sources", [])
})
```

3. **Include history in subsequent requests:**
```python
requests.post(url, json={
    "question": next_question,
    "history": history  # ← Add this
})
```

## Next Steps

Potential future enhancements:
- [ ] Persistent session storage (Redis/PostgreSQL)
- [ ] Automatic history summarization for long conversations
- [ ] Smart history pruning based on relevance
- [ ] History search and analytics
- [ ] Session replay and export

## References

- [DSPy History Documentation](https://dspy.ai/tutorials/conversation_history/)
- [DSPy Agent Tutorial](https://dspy.ai/tutorials/customer_service_agent/)
- [DSPy API Reference](https://dspy.ai/api/primitives/History/)

## Summary

✨ **The agent now has memory!** ✨

The OpenTA Agent can now maintain context across multiple conversation turns, providing a more natural and efficient research experience. The implementation follows DSPy best practices and is fully backwards compatible with existing clients.

Total files modified: 4
Total files created: 4
Total lines of code added: ~500+
Total lines of documentation: ~1000+
