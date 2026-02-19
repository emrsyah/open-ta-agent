# Frontend-Backend Integration Guide

Complete guide for integrating your frontend with the OpenTA Agent backend, including streaming, session management, and best practices.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Conversation Session Management](#conversation-session-management)
3. [Streaming Implementation](#streaming-implementation)
4. [Complete Integration Examples](#complete-integration-examples)
5. [State Management](#state-management)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Common Patterns](#common-patterns)

---

## Quick Start

### API Endpoint

```
POST http://localhost:8000/chat/basic
```

### Request Format

```json
{
  "query": "Your question here",
  "meta_params": {
    "mode": "basic",
    "stream": true,
    "language": "id-ID",
    "timezone": "Asia/Jakarta",
    "source_preference": "all",
    "conversation_id": "optional-uuid-here",
    "is_incognito": false,
    "attachments": []
  }
}
```

### Response Types

**Non-Streaming (stream: false):**
```json
{
  "answer": "Complete answer text",
  "sources": ["Paper_123", "Paper_456"],
  "context": "Chain-of-thought reasoning",
  "search_query": "optimized search keywords"
}
```

**Streaming (stream: true):**
Server-Sent Events (SSE) with chunks:
```
data: {"type":"token","content":"Hello"}

data: {"type":"token","content":" world"}

data: {"type":"done","content":"Hello world","sources":["Paper_123"]}

data: [DONE]
```

---

## Conversation Session Management

### How It Works

```
┌─────────────────────────────────────────────────────┐
│  Frontend                                           │
│  ┌─────────────────────────────────────┐           │
│  │  1. User sends first message        │           │
│  │     (no conversation_id)            │           │
│  └──────────────┬──────────────────────┘           │
│                 │                                   │
│                 ▼                                   │
│  ┌─────────────────────────────────────┐           │
│  │  2. Generate UUID on frontend       │           │
│  │     conversation_id = uuid()        │           │
│  └──────────────┬──────────────────────┘           │
│                 │                                   │
└─────────────────┼───────────────────────────────────┘
                  │
                  ▼  Send with conversation_id
┌─────────────────────────────────────────────────────┐
│  Backend (Redis + Optional DB)                      │
│  ┌─────────────────────────────────────┐           │
│  │  3. Check if conversation exists    │           │
│  │     - If NO: Create new session     │           │
│  │     - If YES: Load history          │           │
│  └──────────────┬──────────────────────┘           │
│                 │                                   │
│                 ▼                                   │
│  ┌─────────────────────────────────────┐           │
│  │  4. Process with LLM + history      │           │
│  └──────────────┬──────────────────────┘           │
│                 │                                   │
│                 ▼                                   │
│  ┌─────────────────────────────────────┐           │
│  │  5. Save to Redis                   │           │
│  │     conversation:{id} = [messages]  │           │
│  │     TTL: 1 hour                     │           │
│  └──────────────┬──────────────────────┘           │
│                 │                                   │
└─────────────────┼───────────────────────────────────┘
                  │
                  ▼  Return response
┌─────────────────────────────────────────────────────┐
│  Frontend                                           │
│  ┌─────────────────────────────────────┐           │
│  │  6. Store conversation_id           │           │
│  │     Keep for follow-up messages     │           │
│  └─────────────────────────────────────┘           │
└─────────────────────────────────────────────────────┘
```

### Session ID Generation: Frontend or Backend?

**✅ Recommended: Frontend generates the ID**

**Why?**
1. **Immediate availability** - No need to wait for backend response
2. **Client control** - Frontend manages session lifecycle
3. **Offline support** - Can prepare messages before sending
4. **Simpler flow** - No need for special "first message" handling

### Implementation

#### Option 1: Frontend Generates ID (Recommended) ⭐

```typescript
// Frontend (React/Next.js)
import { v4 as uuidv4 } from 'uuid';

function ChatComponent() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const startNewConversation = () => {
    // Frontend generates UUID
    const newId = uuidv4();
    setConversationId(newId);
    setMessages([]);
  };

  const sendMessage = async (query: string) => {
    // Use existing conversation_id, or create new one
    const convId = conversationId || uuidv4();
    
    if (!conversationId) {
      setConversationId(convId);
    }

    const response = await fetch('/chat/basic', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        meta_params: {
          conversation_id: convId,  // ← Frontend-generated
          stream: true
        }
      })
    });

    // Handle response...
  };

  return (
    <div>
      <button onClick={startNewConversation}>New Chat</button>
      {/* Chat UI */}
    </div>
  );
}
```

#### Option 2: Backend Generates ID

If you prefer backend to generate:

```typescript
// Frontend
const sendMessage = async (query: string, isFirstMessage: boolean) => {
  const response = await fetch('/chat/basic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      meta_params: {
        conversation_id: isFirstMessage ? null : conversationId,
        stream: false
      }
    })
  });

  const data = await response.json();
  
  // Backend returns conversation_id in response
  if (isFirstMessage && data.conversation_id) {
    setConversationId(data.conversation_id);
  }
};
```

**Backend modification needed:**
```python
# In chat.py
if not conversation_id:
    conversation_id = str(uuid.uuid4())
    # Create session in Redis

return ChatResponse(
    answer=result["answer"],
    sources=result["sources"],
    conversation_id=conversation_id  # ← Return ID
)
```

**⚠️ Downside:** Streaming responses don't easily return JSON metadata.

---

## Streaming Implementation

### How SSE (Server-Sent Events) Works

```
Client                          Server
  │                               │
  │  POST /chat/basic            │
  │  (stream: true)              │
  ├──────────────────────────────>│
  │                               │
  │  HTTP 200 OK                 │
  │  Content-Type: text/event-stream
  │<──────────────────────────────┤
  │                               │
  │  data: {"type":"token",...}  │
  │<──────────────────────────────┤
  │                               │
  │  data: {"type":"token",...}  │
  │<──────────────────────────────┤
  │                               │
  │  data: {"type":"done",...}   │
  │<──────────────────────────────┤
  │                               │
  │  data: [DONE]                │
  │<──────────────────────────────┤
  │                               │
  │  Connection closed           │
  └───────────────────────────────┘
```

### Vanilla JavaScript Example

```javascript
async function streamChat(query, conversationId) {
  const response = await fetch('http://localhost:8000/chat/basic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      meta_params: {
        stream: true,
        conversation_id: conversationId
      }
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const dataStr = line.slice(6);
        if (dataStr === '[DONE]') return;

        try {
          const data = JSON.parse(dataStr);
          handleStreamChunk(data);
        } catch (e) {
          console.error('Parse error:', e);
        }
      }
    }
  }
}

function handleStreamChunk(data) {
  switch (data.type) {
    case 'token':
      // Append token to UI
      appendToken(data.content);
      break;
    case 'done':
      // Show final answer and sources
      showSources(data.sources);
      break;
    case 'error':
      // Show error
      showError(data.content);
      break;
  }
}
```

### React Hook for Streaming

```typescript
// hooks/useStreamingChat.ts
import { useState, useCallback } from 'react';

interface StreamChunk {
  type: 'token' | 'done' | 'error' | 'rationale';
  content?: string;
  sources?: string[];
}

export function useStreamingChat(conversationId: string) {
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (query: string) => {
    setAnswer('');
    setSources([]);
    setError(null);
    setIsStreaming(true);

    try {
      const response = await fetch('/chat/basic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          meta_params: {
            stream: true,
            conversation_id: conversationId
          }
        })
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') {
              setIsStreaming(false);
              return;
            }

            try {
              const data: StreamChunk = JSON.parse(dataStr);

              if (data.type === 'token') {
                setAnswer(prev => prev + data.content);
              } else if (data.type === 'done') {
                setSources(data.sources || []);
              } else if (data.type === 'error') {
                setError(data.content || 'Unknown error');
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
      setIsStreaming(false);
    }
  }, [conversationId]);

  return {
    answer,
    sources,
    isStreaming,
    error,
    sendMessage
  };
}

// Usage in component
function ChatMessage({ query, conversationId }) {
  const { answer, sources, isStreaming, sendMessage } = useStreamingChat(conversationId);

  useEffect(() => {
    sendMessage(query);
  }, [query, sendMessage]);

  return (
    <div>
      <div className="answer">
        {answer}
        {isStreaming && <span className="cursor">▊</span>}
      </div>
      {sources.length > 0 && (
        <div className="sources">
          📄 {sources.join(', ')}
        </div>
      )}
    </div>
  );
}
```

### Next.js App Router Example

```typescript
// app/chat/page.tsx
'use client';

import { useState } from 'react';
import { v4 as uuidv4 } from 'uuid';

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string>(() => uuidv4());
  const [messages, setMessages] = useState<Array<{
    role: 'user' | 'assistant';
    content: string;
    sources?: string[];
  }>>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    // Add user message
    const userMessage = { role: 'user' as const, content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);

    // Start streaming assistant response
    let assistantContent = '';
    let assistantSources: string[] = [];

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: input,
          meta_params: {
            stream: true,
            conversation_id: conversationId,
            language: 'id-ID'
          }
        })
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      // Add empty assistant message
      const messageIndex = messages.length + 1;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '',
        sources: []
      }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') {
              setIsStreaming(false);
              break;
            }

            try {
              const data = JSON.parse(dataStr);

              if (data.type === 'token') {
                assistantContent += data.content;
                setMessages(prev => {
                  const newMessages = [...prev];
                  newMessages[messageIndex] = {
                    ...newMessages[messageIndex],
                    content: assistantContent
                  };
                  return newMessages;
                });
              } else if (data.type === 'done') {
                assistantSources = data.sources || [];
                setMessages(prev => {
                  const newMessages = [...prev];
                  newMessages[messageIndex] = {
                    ...newMessages[messageIndex],
                    sources: assistantSources
                  };
                  return newMessages;
                });
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Stream error:', error);
      setIsStreaming(false);
    }
  };

  const startNewConversation = () => {
    setConversationId(uuidv4());
    setMessages([]);
  };

  return (
    <div className="chat-container">
      <div className="header">
        <h1>OpenTA Agent</h1>
        <button onClick={startNewConversation}>New Chat</button>
      </div>

      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="content">{msg.content}</div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                📄 {msg.sources.join(', ')}
              </div>
            )}
          </div>
        ))}
        {isStreaming && (
          <div className="message assistant">
            <div className="content">
              <span className="typing-indicator">▊</span>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          disabled={isStreaming}
        />
        <button type="submit" disabled={isStreaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
```

---

## Complete Integration Examples

### Example 1: Simple Chat Application

```typescript
// types.ts
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  timestamp: Date;
}

export interface ChatSession {
  conversationId: string;
  messages: Message[];
  createdAt: Date;
}

// chatService.ts
import { v4 as uuidv4 } from 'uuid';

class ChatService {
  private baseUrl = 'http://localhost:8000';

  async sendMessage(
    query: string,
    conversationId: string,
    options: {
      stream?: boolean;
      language?: string;
      sourcePreference?: string;
    } = {}
  ): Promise<Response> {
    return fetch(`${this.baseUrl}/chat/basic`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        meta_params: {
          stream: options.stream ?? true,
          conversation_id: conversationId,
          language: options.language ?? 'id-ID',
          source_preference: options.sourcePreference ?? 'all',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        }
      })
    });
  }

  async *streamMessage(
    query: string,
    conversationId: string
  ): AsyncGenerator<{ type: string; content?: string; sources?: string[] }> {
    const response = await this.sendMessage(query, conversationId, { stream: true });
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6);
          if (dataStr === '[DONE]') return;

          try {
            yield JSON.parse(dataStr);
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    }
  }
}

export const chatService = new ChatService();

// ChatProvider.tsx
import { createContext, useContext, useState, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { chatService } from './chatService';

interface ChatContextType {
  sessions: ChatSession[];
  currentSession: ChatSession | null;
  createSession: () => void;
  sendMessage: (query: string) => Promise<void>;
  isStreaming: boolean;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const createSession = useCallback(() => {
    const newSession: ChatSession = {
      conversationId: uuidv4(),
      messages: [],
      createdAt: new Date()
    };
    setSessions(prev => [...prev, newSession]);
    setCurrentSession(newSession);
  }, []);

  const sendMessage = useCallback(async (query: string) => {
    if (!currentSession || isStreaming) return;

    // Add user message
    const userMessage: Message = {
      id: uuidv4(),
      role: 'user',
      content: query,
      timestamp: new Date()
    };

    setCurrentSession(prev => ({
      ...prev!,
      messages: [...prev!.messages, userMessage]
    }));

    setIsStreaming(true);

    // Stream assistant response
    const assistantMessage: Message = {
      id: uuidv4(),
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };

    setCurrentSession(prev => ({
      ...prev!,
      messages: [...prev!.messages, assistantMessage]
    }));

    try {
      for await (const chunk of chatService.streamMessage(
        query,
        currentSession.conversationId
      )) {
        if (chunk.type === 'token') {
          assistantMessage.content += chunk.content;
          setCurrentSession(prev => ({
            ...prev!,
            messages: prev!.messages.map(m =>
              m.id === assistantMessage.id ? { ...assistantMessage } : m
            )
          }));
        } else if (chunk.type === 'done') {
          assistantMessage.sources = chunk.sources;
          setCurrentSession(prev => ({
            ...prev!,
            messages: prev!.messages.map(m =>
              m.id === assistantMessage.id ? { ...assistantMessage } : m
            )
          }));
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
    } finally {
      setIsStreaming(false);
    }
  }, [currentSession, isStreaming]);

  return (
    <ChatContext.Provider value={{
      sessions,
      currentSession,
      createSession,
      sendMessage,
      isStreaming
    }}>
      {children}
    </ChatContext.Provider>
  );
}

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) throw new Error('useChat must be used within ChatProvider');
  return context;
};
```

---

## State Management

### Option 1: Local State (React Context)

```typescript
// For simple apps - shown above in ChatProvider
```

### Option 2: Zustand

```typescript
// store/chatStore.ts
import create from 'zustand';
import { persist } from 'zustand/middleware';

interface ChatStore {
  conversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
  
  setConversationId: (id: string) => void;
  addMessage: (message: Message) => void;
  updateLastMessage: (content: string) => void;
  setStreaming: (streaming: boolean) => void;
  clearChat: () => void;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      conversationId: null,
      messages: [],
      isStreaming: false,

      setConversationId: (id) => set({ conversationId: id }),
      
      addMessage: (message) => set((state) => ({
        messages: [...state.messages, message]
      })),
      
      updateLastMessage: (content) => set((state) => ({
        messages: state.messages.map((msg, i) =>
          i === state.messages.length - 1
            ? { ...msg, content: msg.content + content }
            : msg
        )
      })),
      
      setStreaming: (streaming) => set({ isStreaming: streaming }),
      
      clearChat: () => set({
        conversationId: null,
        messages: [],
        isStreaming: false
      })
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        conversationId: state.conversationId,
        messages: state.messages
      })
    }
  )
);
```

### Option 3: Redux Toolkit

```typescript
// features/chat/chatSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface ChatState {
  conversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
}

const initialState: ChatState = {
  conversationId: null,
  messages: [],
  isStreaming: false
};

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setConversationId: (state, action: PayloadAction<string>) => {
      state.conversationId = action.payload;
    },
    addMessage: (state, action: PayloadAction<Message>) => {
      state.messages.push(action.payload);
    },
    appendToLastMessage: (state, action: PayloadAction<string>) => {
      const lastMessage = state.messages[state.messages.length - 1];
      if (lastMessage) {
        lastMessage.content += action.payload;
      }
    },
    setStreaming: (state, action: PayloadAction<boolean>) => {
      state.isStreaming = action.payload;
    },
    clearChat: (state) => {
      state.conversationId = null;
      state.messages = [];
      state.isStreaming = false;
    }
  }
});

export const {
  setConversationId,
  addMessage,
  appendToLastMessage,
  setStreaming,
  clearChat
} = chatSlice.actions;

export default chatSlice.reducer;
```

---

## Error Handling

### Network Errors

```typescript
async function sendMessageWithRetry(
  query: string,
  conversationId: string,
  maxRetries = 3
) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch('/chat/basic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          meta_params: { conversation_id: conversationId }
        }),
        signal: AbortSignal.timeout(30000) // 30s timeout
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response;
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;
      
      // Exponential backoff
      await new Promise(resolve => 
        setTimeout(resolve, 1000 * Math.pow(2, attempt))
      );
    }
  }
}
```

### Streaming Errors

```typescript
function handleStreamError(error: Error) {
  if (error.name === 'AbortError') {
    return 'Request timed out';
  } else if (error.message.includes('network')) {
    return 'Network connection lost';
  } else {
    return 'An unexpected error occurred';
  }
}
```

---

## Best Practices

### 1. Session Management

✅ **DO:**
- Generate conversation_id on frontend (UUID v4)
- Store conversation_id in component state or global store
- Clear conversation_id when starting new chat
- Persist conversation_id to localStorage for page refreshes

❌ **DON'T:**
- Use user IDs as conversation IDs
- Share conversation IDs between different chats
- Store sensitive data in conversation ID

### 2. Performance

✅ **DO:**
- Use streaming for better perceived performance
- Implement request cancellation
- Show loading states
- Cache recent conversations

❌ **DON'T:**
- Send entire history in every request (backend handles this)
- Make parallel requests to same conversation
- Forget to clean up event listeners

### 3. UX

✅ **DO:**
- Show typing indicator during streaming
- Display sources prominently
- Allow cancelling long responses
- Show error messages clearly
- Auto-scroll to new messages

❌ **DON'T:**
- Block UI during requests
- Hide error messages
- Allow sending while streaming

---

## Common Patterns

### Pattern 1: Persisting Conversations

```typescript
// Save to localStorage
function saveConversation(session: ChatSession) {
  localStorage.setItem(
    `conversation_${session.conversationId}`,
    JSON.stringify({
      conversationId: session.conversationId,
      messages: session.messages,
      createdAt: session.createdAt
    })
  );
}

// Load from localStorage
function loadConversation(conversationId: string): ChatSession | null {
  const data = localStorage.getItem(`conversation_${conversationId}`);
  return data ? JSON.parse(data) : null;
}

// List all conversations
function listConversations(): ChatSession[] {
  const sessions: ChatSession[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith('conversation_')) {
      const data = localStorage.getItem(key);
      if (data) sessions.push(JSON.parse(data));
    }
  }
  return sessions.sort((a, b) => 
    new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  );
}
```

### Pattern 2: Typing Indicators

```typescript
function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <span></span>
      <span></span>
      <span></span>
    </div>
  );
}

// CSS
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #999;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; }
  30% { opacity: 1; }
}
```

### Pattern 3: Request Cancellation

```typescript
function useCancellableStream() {
  const abortControllerRef = useRef<AbortController | null>(null);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const streamMessage = useCallback(async (query: string, conversationId: string) => {
    // Cancel previous stream if any
    cancelStream();

    // Create new abort controller
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('/chat/basic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          meta_params: { stream: true, conversation_id: conversationId }
        }),
        signal: abortControllerRef.current.signal
      });

      // Process stream...
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Stream cancelled');
      } else {
        throw error;
      }
    }
  }, [cancelStream]);

  return { streamMessage, cancelStream };
}
```

---

## Summary Checklist

### Frontend Setup
- [ ] Install UUID library: `npm install uuid`
- [ ] Create chat service/API wrapper
- [ ] Set up state management (Context/Zustand/Redux)
- [ ] Implement streaming handler
- [ ] Add error handling and retry logic

### Session Management
- [ ] Generate conversation_id on frontend (UUID)
- [ ] Send conversation_id in every request
- [ ] Store conversation_id in state
- [ ] Persist to localStorage (optional)
- [ ] Clear on "New Chat"

### Streaming
- [ ] Use fetch with `stream: true`
- [ ] Parse SSE format correctly
- [ ] Handle different chunk types (token, done, error)
- [ ] Show typing indicator
- [ ] Update UI progressively

### Error Handling
- [ ] Network error handling
- [ ] Timeout handling
- [ ] Stream interruption handling
- [ ] Show error messages to user

### UX Enhancements
- [ ] Auto-scroll to new messages
- [ ] Show sources
- [ ] Typing indicators
- [ ] Request cancellation
- [ ] Loading states

---

## Quick Reference

### Conversation Flow
```
1. User starts chat → Frontend generates UUID
2. User sends message → Include conversation_id in request
3. Backend checks Redis → Loads history if exists
4. Backend processes with LLM → Uses history for context
5. Backend saves to Redis → Stores message in session
6. Frontend receives response → Updates UI
7. Repeat steps 2-6 for follow-ups
```

### When to Create New Conversation ID
- ✅ User clicks "New Chat"
- ✅ User explicitly starts new topic
- ✅ After long inactivity (optional)
- ❌ NOT on every message
- ❌ NOT on page refresh (load from storage)

### Session Expiry
- **Backend (Redis TTL):** 1 hour by default
- **Frontend (localStorage):** Keep indefinitely
- **If expired on backend:** Creates new session with same ID

---

Need help with a specific integration? Check the examples above or ask for clarification!
