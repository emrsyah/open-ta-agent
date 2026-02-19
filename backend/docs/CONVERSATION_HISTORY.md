# Conversation History Management

This document explains how the OpenTA Agent maintains conversation history for context-aware responses using DSPy's `dspy.History` utility.

## Overview

The agent now supports multi-turn conversations with memory, allowing it to:
- Reference previous questions and answers
- Maintain context across conversation turns
- Provide more coherent and contextual responses
- Build on previous discussions about research papers

## Architecture

### 1. Data Models

**ConversationMessage** - Represents a single turn in the conversation:
```python
{
    "question": "What is machine learning?",
    "answer": "Machine learning is...",
    "sources": ["paper_001", "paper_002"],
    "context": "Retrieved paper context..."
}
```

**ChatRequest** - Now includes optional history field:
```python
{
    "question": "Tell me more about that",
    "stream": true,
    "session_id": "user_123",
    "history": [
        {
            "question": "What is machine learning?",
            "answer": "Machine learning is...",
            "sources": ["paper_001"]
        }
    ]
}
```

### 2. DSPy Integration

The system uses `dspy.History` to pass conversation context to the language model:

```python
# In PaperChatSignature
class PaperChatSignature(dspy.Signature):
    question: str = dspy.InputField()
    context: str = dspy.InputField()
    history: dspy.History = dspy.InputField()  # 👈 Conversation history
    answer: str = dspy.OutputField()
    sources: List[str] = dspy.OutputField()
```

The history is formatted according to DSPy's conventions, allowing the model to see previous conversation turns in a structured way.

### 3. Conversion Flow

```
Client Request (JSON)
    ↓
ConversationMessage[] in ChatRequest
    ↓
RAGService._convert_to_dspy_history()
    ↓
dspy.History(messages=[...])
    ↓
PaperRAG.forward() with history
    ↓
LLM with full conversation context
```

## Usage Examples

### Example 1: Basic Conversation Flow

**First Turn (No History):**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What papers discuss transformer models?",
    "stream": false
  }'
```

Response:
```json
{
  "answer": "Several papers discuss transformer models including Paper_123 which covers...",
  "sources": ["Paper_123", "Paper_456"],
  "search_query": "transformer models architecture"
}
```

**Second Turn (With History):**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Which one is most recent?",
    "stream": false,
    "history": [
      {
        "question": "What papers discuss transformer models?",
        "answer": "Several papers discuss transformer models including Paper_123 which covers...",
        "sources": ["Paper_123", "Paper_456"]
      }
    ]
  }'
```

Response:
```json
{
  "answer": "Among the transformer papers we discussed, Paper_456 is the most recent (2024)...",
  "sources": ["Paper_456"]
}
```

### Example 2: Multi-Turn Research Session

```python
import requests

BASE_URL = "http://localhost:8000"
conversation_history = []

def chat(question):
    """Send a question with conversation history"""
    response = requests.post(
        f"{BASE_URL}/chat/basic",
        json={
            "question": question,
            "stream": False,
            "history": conversation_history
        }
    )
    result = response.json()
    
    # Add this turn to history for next question
    conversation_history.append({
        "question": question,
        "answer": result["answer"],
        "sources": result.get("sources", [])
    })
    
    return result

# Turn 1
response1 = chat("What is deep learning?")
print(response1["answer"])

# Turn 2 - Agent knows context from Turn 1
response2 = chat("What are its main applications?")
print(response2["answer"])

# Turn 3 - Agent remembers both previous turns
response3 = chat("Which paper covers CNNs in that context?")
print(response3["answer"])
```

### Example 3: Streaming with History

```python
import requests
import json

def chat_stream_with_history(question, history):
    """Stream response with conversation history"""
    response = requests.post(
        "http://localhost:8000/chat/basic",
        json={
            "question": question,
            "stream": True,
            "history": history
        },
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])
                if data.get("type") == "token":
                    print(data["content"], end="", flush=True)
                elif data.get("type") == "done":
                    print("\n\nSources:", data.get("sources"))

# Use it
history = [
    {
        "question": "Tell me about GANs",
        "answer": "GANs (Generative Adversarial Networks) are...",
        "sources": ["Paper_789"]
    }
]

chat_stream_with_history("What are their limitations?", history)
```

## Frontend Integration

### React Example

```typescript
import { useState } from 'react';

interface Message {
  question: string;
  answer: string;
  sources?: string[];
}

function ChatComponent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');

  const sendMessage = async () => {
    const response = await fetch('http://localhost:8000/chat/basic', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: input,
        stream: false,
        history: messages  // Send entire conversation history
      })
    });

    const result = await response.json();
    
    // Add the new turn to messages
    setMessages([
      ...messages,
      {
        question: input,
        answer: result.answer,
        sources: result.sources
      }
    ]);
    
    setInput('');
  };

  return (
    <div>
      {messages.map((msg, i) => (
        <div key={i}>
          <p><strong>You:</strong> {msg.question}</p>
          <p><strong>Agent:</strong> {msg.answer}</p>
          {msg.sources && <p>📄 {msg.sources.join(', ')}</p>}
        </div>
      ))}
      <input 
        value={input} 
        onChange={(e) => setInput(e.target.value)} 
      />
      <button onClick={sendMessage}>Send</button>
    </div>
  );
}
```

## Best Practices

### 1. History Management

**✅ DO:**
- Keep history for the current conversation session
- Clear history when starting a new topic
- Limit history to recent turns (last 5-10 messages) to avoid context overflow
- Store session_id for tracking different conversations

**❌ DON'T:**
- Send entire conversation history from weeks ago
- Mix unrelated conversation sessions
- Include sensitive information in history

### 2. History Pruning

For long conversations, implement history pruning:

```python
def prune_history(history, max_turns=10):
    """Keep only the most recent turns"""
    if len(history) > max_turns:
        return history[-max_turns:]
    return history

# Usage
pruned_history = prune_history(conversation_history, max_turns=8)
```

### 3. Session Management

Implement proper session tracking:

```python
sessions = {}

def get_session_history(session_id):
    """Get or create session history"""
    if session_id not in sessions:
        sessions[session_id] = []
    return sessions[session_id]

def add_to_session(session_id, message):
    """Add message to session history"""
    history = get_session_history(session_id)
    history.append(message)
    
    # Prune if too long
    if len(history) > 10:
        sessions[session_id] = history[-10:]
```

## How It Works Internally

### 1. History Conversion

When a request arrives, the RAG service converts the JSON history to DSPy format:

```python
def _convert_to_dspy_history(self, history_messages):
    """Convert from ChatRequest format to dspy.History"""
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

### 2. Prompt Construction

DSPy automatically formats the history into the prompt. The LLM sees:

```
System message:
You are 'OpenTA Agent', a specialized research assistant...

User message (Turn 1):
[[ ## question ## ]]
What is machine learning?

[[ ## context ## ]]
[Paper abstracts...]

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

Respond with the corresponding output fields...
```

### 3. Context-Aware Responses

The model can now:
- Use pronouns ("it", "that", "those") referring to previous topics
- Build incrementally on previous answers
- Reference specific papers mentioned earlier
- Maintain coherent multi-turn research sessions

## Performance Considerations

### Token Usage

Each history turn adds tokens to the prompt. Monitor and limit:
- **Good:** 5-10 recent turns (~2-5K tokens)
- **Warning:** 20+ turns (~10K+ tokens)
- **Bad:** Unlimited history (exceeds context window)

### Caching

Consider implementing LRU cache for sessions:

```python
from functools import lru_cache
from datetime import datetime, timedelta

class SessionCache:
    def __init__(self, max_age_minutes=30):
        self.sessions = {}
        self.max_age = timedelta(minutes=max_age_minutes)
    
    def get(self, session_id):
        if session_id in self.sessions:
            session, timestamp = self.sessions[session_id]
            if datetime.now() - timestamp < self.max_age:
                return session
            else:
                del self.sessions[session_id]
        return []
    
    def set(self, session_id, history):
        self.sessions[session_id] = (history, datetime.now())
```

## Testing

Test the history feature:

```bash
# Test 1: No history (should work as before)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?", "stream": false}'

# Test 2: With empty history (should work)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?", "stream": false, "history": []}'

# Test 3: With history (should reference previous context)
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

## Troubleshooting

### Issue: Model ignores history

**Solution:** Check that:
1. History is properly formatted in the request
2. `dspy.History` is included in the signature
3. The LM supports long context windows

### Issue: Responses are inconsistent

**Solution:** 
1. Limit history length (prune old messages)
2. Clear history when changing topics
3. Ensure sources are included in history for better context

### Issue: High latency

**Solution:**
1. Reduce history length
2. Use a cheaper model for intent classification
3. Implement caching for repeated sessions

## Future Enhancements

Potential improvements:
- 🔄 Automatic history summarization for long conversations
- 💾 Persistent session storage (database)
- 🧹 Smart history pruning (keep only relevant turns)
- 📊 History analytics and insights
- 🔍 Semantic search over conversation history

## References

- [DSPy History Documentation](https://dspy.ai/tutorials/conversation_history/)
- [DSPy Agent Tutorial](https://dspy.ai/tutorials/customer_service_agent/)
- [DSPy API Reference](https://dspy.ai/api/primitives/History/)
