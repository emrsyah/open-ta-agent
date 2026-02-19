# API Migration Guide: New meta_params Structure

## Overview

We've restructured the chat API to provide a cleaner, more scalable interface with better parameter organization.

## What Changed?

### Old API Structure ❌

```json
{
  "question": "What is machine learning?",
  "stream": true,
  "session_id": "abc-123",
  "mode": "basic"
}
```

### New API Structure ✅

```json
{
  "query": "What is machine learning?",
  "meta_params": {
    "mode": "basic",
    "stream": true,
    "attachments": [],
    "is_incognito": false,
    "timezone": "Asia/Jakarta",
    "language": "id-ID",
    "source_preference": "all",
    "conversation_id": "abc-123"
  }
}
```

## Why the Change?

1. **Better Organization** - Separates query from metadata
2. **Extensibility** - Easy to add new parameters without cluttering top level
3. **Clarity** - Clear distinction between user input and request configuration
4. **Standards** - Follows REST API best practices

## Detailed Changes

### Field Mapping

| Old Field | New Location | Notes |
|-----------|--------------|-------|
| `question` | `query` | Renamed for clarity |
| `stream` | `meta_params.stream` | Moved to metadata |
| `session_id` | `meta_params.conversation_id` | Renamed and moved |
| `mode` | `meta_params.mode` | Moved to metadata |
| N/A | `meta_params.attachments` | **NEW** - For file uploads |
| N/A | `meta_params.is_incognito` | **NEW** - Private mode |
| N/A | `meta_params.timezone` | **NEW** - User timezone |
| N/A | `meta_params.language` | **NEW** - Preferred language |
| N/A | `meta_params.source_preference` | **NEW** - Source filtering |

### New Parameters Explained

#### `attachments` (Array)
```json
"attachments": [
  "https://example.com/paper.pdf",
  "file_id_123"
]
```
- **Purpose:** Attach files/documents to the conversation
- **Status:** Reserved for future implementation
- **Default:** `[]` (empty array)

#### `is_incognito` (Boolean)
```json
"is_incognito": true
```
- **Purpose:** When `true`, conversation won't be saved to history
- **Use Cases:** 
  - Privacy-sensitive queries
  - Testing
  - Anonymous usage
- **Default:** `false`

#### `timezone` (String)
```json
"timezone": "Asia/Jakarta"
```
- **Purpose:** User's timezone for context-aware responses
- **Format:** IANA timezone identifier
- **Examples:** `"America/New_York"`, `"Europe/London"`, `"UTC"`
- **Default:** `"UTC"`

#### `language` (String)
```json
"language": "id-ID"
```
- **Purpose:** Preferred response language
- **Format:** BCP 47 language tag
- **Examples:** `"en-US"`, `"id-ID"`, `"zh-CN"`
- **Default:** `"en-US"`

#### `source_preference` (String)
```json
"source_preference": "only_papers"
```
- **Purpose:** Filter which sources the agent uses
- **Options:**
  - `"all"` - Use all available sources
  - `"only_papers"` - Only use research papers
  - `"only_general"` - Only use general knowledge
- **Default:** `"all"`

#### `conversation_id` (String)
```json
"conversation_id": "conv_abc123"
```
- **Purpose:** Continue an existing conversation
- **Behavior:**
  - If provided: Load history from Redis/DB
  - If `null`: Start new conversation
  - With `is_incognito=true`: Ignored (no history)
- **Format:** UUID or custom string
- **Default:** `null`

## Migration Examples

### Example 1: Basic Query

**Before:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is AI?",
    "stream": false
  }'
```

**After:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is AI?",
    "meta_params": {
      "stream": false
    }
  }'
```

### Example 2: Streaming with Session

**Before:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Tell me more",
    "stream": true,
    "session_id": "session_123"
  }'
```

**After:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tell me more",
    "meta_params": {
      "stream": true,
      "conversation_id": "session_123"
    }
  }'
```

### Example 3: Indonesian Language

**Before:**
```bash
# Not supported
```

**After:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Apa itu kecerdasan buatan?",
    "meta_params": {
      "language": "id-ID",
      "timezone": "Asia/Jakarta"
    }
  }'
```

### Example 4: Research-Only Mode

**Before:**
```bash
# Not supported
```

**After:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What papers discuss neural networks?",
    "meta_params": {
      "source_preference": "only_papers",
      "stream": false
    }
  }'
```

### Example 5: Incognito Mode

**Before:**
```bash
# Not supported
```

**After:**
```bash
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Sensitive question here",
    "meta_params": {
      "is_incognito": true
    }
  }'
```

## Client Code Migration

### JavaScript/TypeScript

**Before:**
```typescript
const response = await fetch('/chat/basic', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    question: userInput,
    stream: true,
    session_id: sessionId
  })
});
```

**After:**
```typescript
const response = await fetch('/chat/basic', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: userInput,
    meta_params: {
      stream: true,
      conversation_id: sessionId,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
    }
  })
});
```

### Python

**Before:**
```python
import requests

response = requests.post(
    'http://localhost:8000/chat/basic',
    json={
        'question': 'What is AI?',
        'stream': False,
        'session_id': 'abc123'
    }
)
```

**After:**
```python
import requests

response = requests.post(
    'http://localhost:8000/chat/basic',
    json={
        'query': 'What is AI?',
        'meta_params': {
            'stream': False,
            'conversation_id': 'abc123',
            'language': 'en-US'
        }
    }
)
```

### React Example

**Before:**
```tsx
const [messages, setMessages] = useState([]);

const sendMessage = async (question: string) => {
  const response = await fetch('/chat/basic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      stream: false
    })
  });
  
  const result = await response.json();
  setMessages([...messages, { question, answer: result.answer }]);
};
```

**After:**
```tsx
const [messages, setMessages] = useState([]);
const [conversationId, setConversationId] = useState(null);

const sendMessage = async (query: string) => {
  const response = await fetch('/chat/basic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      meta_params: {
        stream: false,
        conversation_id: conversationId,
        language: 'id-ID',
        timezone: 'Asia/Jakarta'
      }
    })
  });
  
  const result = await response.json();
  
  // Store conversation ID for session continuity
  if (!conversationId && result.conversation_id) {
    setConversationId(result.conversation_id);
  }
  
  setMessages([...messages, { question: query, answer: result.answer }]);
};
```

## Backwards Compatibility

✅ **Good news:** The old API format still works!

The backend supports both old and new formats for a smooth migration:

```python
# In ChatRequest model
def get_query(self) -> str:
    """Get query with backwards compatibility."""
    return self.query or self.question or ""

def get_stream(self) -> bool:
    """Get stream preference with backwards compatibility."""
    if self.stream is not None:
        return self.stream
    return self.meta_params.stream
```

### Deprecation Timeline

- **Now:** Both old and new formats work
- **Next release:** Warning logs for old format
- **In 3 months:** Old format deprecated (still works with warnings)
- **In 6 months:** Old format removed

## Migration Checklist

- [ ] Update API calls to use `query` instead of `question`
- [ ] Move `stream`, `mode`, `session_id` to `meta_params`
- [ ] Rename `session_id` to `conversation_id`
- [ ] Add `language` preference if supporting multilingual
- [ ] Add `timezone` if showing timestamps
- [ ] Implement `is_incognito` for privacy-sensitive features
- [ ] Use `source_preference` if filtering sources
- [ ] Test both streaming and non-streaming modes
- [ ] Update TypeScript/API types
- [ ] Update documentation/examples

## Testing

### Test the New API

```bash
# Test basic query
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test message",
    "meta_params": {
      "stream": false,
      "language": "en-US"
    }
  }'

# Test backwards compatibility (old format)
curl -X POST http://localhost:8000/chat/basic \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Test message",
    "stream": false
  }'
```

Both should work! ✅

## TypeScript Types

```typescript
// New types
interface ChatMetaParams {
  mode?: 'basic' | 'deep';
  stream?: boolean;
  attachments?: string[];
  is_incognito?: boolean;
  timezone?: string;
  language?: string;
  source_preference?: 'all' | 'only_papers' | 'only_general';
  conversation_id?: string | null;
}

interface ChatRequest {
  query: string;
  meta_params?: ChatMetaParams;
}

interface ChatResponse {
  answer: string;
  sources?: string[];
  context?: string;
  search_query?: string;
  conversation_id?: string;
}

// Usage
const request: ChatRequest = {
  query: 'What is AI?',
  meta_params: {
    stream: false,
    language: 'id-ID',
    source_preference: 'only_papers'
  }
};
```

## FAQ

### Q: Do I have to migrate immediately?
**A:** No, the old format still works. But we recommend migrating to take advantage of new features.

### Q: What if I don't specify meta_params?
**A:** Defaults will be used (stream=true, mode='basic', etc.)

### Q: Can I mix old and new formats?
**A:** Yes, but not recommended. The backend will prioritize new format fields.

### Q: How do I know which format the API expects?
**A:** Both work, but the OpenAPI/Swagger docs show the new format.

### Q: Will streaming still work?
**A:** Yes! Just move `"stream": true` to `meta_params.stream`.

### Q: What about the `/chat/deep` endpoint?
**A:** Use `meta_params.mode = "deep"` with `/chat/basic` instead.

## Support

If you encounter issues:
1. Check this migration guide
2. Review examples in `examples/conversation_with_session.py`
3. Check API docs at `/docs`
4. Contact the backend team

## Resources

- [Architecture Guide](./ARCHITECTURE_CONVERSATION_HISTORY.md)
- [Session Manager Documentation](../app/services/session_manager.py)
- [API Examples](../examples/)
- [OpenAPI Docs](http://localhost:8000/docs)
