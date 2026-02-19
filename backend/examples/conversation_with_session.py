"""
Example: Using conversation history with session management (Redis)

This script demonstrates how to use the new meta_params API structure
with Redis-based session management for conversation history.
"""

import requests
import json
import uuid
from typing import Optional

BASE_URL = "http://localhost:8000"


class ConversationClient:
    """Client for managing conversations with the OpenTA Agent"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.conversation_id: Optional[str] = None
    
    def start_conversation(self, conversation_id: Optional[str] = None):
        """Start a new conversation or continue existing one."""
        self.conversation_id = conversation_id or str(uuid.uuid4())
        print(f"📝 Conversation ID: {self.conversation_id}")
        return self.conversation_id
    
    def chat(
        self,
        query: str,
        stream: bool = False,
        mode: str = "basic",
        language: str = "en-US",
        source_preference: str = "all",
        is_incognito: bool = False
    ):
        """
        Send a message using the new meta_params structure.
        
        Args:
            query: Your question
            stream: Whether to stream the response
            mode: Chat mode ('basic' or 'deep')
            language: Language preference ('id-ID', 'en-US')
            source_preference: Source filter ('all', 'only_papers', 'only_general')
            is_incognito: If True, won't save to history
        """
        payload = {
            "query": query,
            "meta_params": {
                "mode": mode,
                "stream": stream,
                "language": language,
                "source_preference": source_preference,
                "is_incognito": is_incognito,
                "conversation_id": self.conversation_id if not is_incognito else None,
                "timezone": "Asia/Jakarta",
                "attachments": []
            }
        }
        
        print(f"\n{'='*70}")
        print(f"💬 You: {query}")
        print(f"📋 Mode: {mode} | Lang: {language} | Sources: {source_preference}")
        if is_incognito:
            print("🕵️  Incognito mode (won't be saved)")
        print(f"{'='*70}")
        
        if not stream:
            return self._chat_non_streaming(payload)
        else:
            return self._chat_streaming(payload)
    
    def _chat_non_streaming(self, payload: dict):
        """Handle non-streaming response."""
        response = requests.post(
            f"{self.base_url}/chat/basic",
            json=payload
        )
        
        result = response.json()
        print(f"🤖 Agent: {result['answer']}")
        
        if result.get('sources'):
            print(f"\n📄 Sources: {', '.join(result['sources'])}")
        
        if result.get('search_query'):
            print(f"🔍 Search Query: {result['search_query']}")
        
        return result
    
    def _chat_streaming(self, payload: dict):
        """Handle streaming response."""
        response = requests.post(
            f"{self.base_url}/chat/basic",
            json=payload,
            stream=True
        )
        
        print("🤖 Agent: ", end="", flush=True)
        answer_parts = []
        sources = []
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "token":
                            content = data["content"]
                            print(content, end="", flush=True)
                            answer_parts.append(content)
                        elif data.get("type") == "done":
                            sources = data.get("sources", [])
                    except json.JSONDecodeError:
                        pass
        
        print()  # New line
        if sources:
            print(f"\n📄 Sources: {', '.join(sources)}")
        
        return {
            "answer": "".join(answer_parts),
            "sources": sources
        }
    
    def end_conversation(self):
        """End the current conversation."""
        print(f"\n✅ Conversation {self.conversation_id} ended")
        self.conversation_id = None


def demo_basic_conversation():
    """Demo 1: Basic conversation with session management"""
    print("\n" + "="*70)
    print("DEMO 1: Basic Conversation with Session Management")
    print("="*70)
    
    client = ConversationClient()
    client.start_conversation()
    
    # Turn 1
    client.chat(
        "What papers discuss machine learning at Telkom University?",
        stream=False
    )
    
    # Turn 2 - Agent remembers context via Redis
    client.chat(
        "Which one is most recent?",
        stream=False
    )
    
    # Turn 3
    client.chat(
        "Can you summarize that paper?",
        stream=False
    )
    
    client.end_conversation()


def demo_multilingual():
    """Demo 2: Indonesian language conversation"""
    print("\n" + "="*70)
    print("DEMO 2: Multilingual Support (Indonesian)")
    print("="*70)
    
    client = ConversationClient()
    client.start_conversation()
    
    # Indonesian conversation
    client.chat(
        "Apa itu machine learning?",
        stream=False,
        language="id-ID"
    )
    
    client.chat(
        "Bagaimana cara kerjanya?",
        stream=False,
        language="id-ID"
    )
    
    client.end_conversation()


def demo_source_preferences():
    """Demo 3: Different source preferences"""
    print("\n" + "="*70)
    print("DEMO 3: Source Preferences")
    print("="*70)
    
    client = ConversationClient()
    
    # Only papers
    client.start_conversation()
    print("\n📚 Source: Only Papers")
    client.chat(
        "What is deep learning?",
        stream=False,
        source_preference="only_papers"
    )
    client.end_conversation()
    
    # All sources
    client.start_conversation()
    print("\n🌐 Source: All Sources")
    client.chat(
        "What is deep learning?",
        stream=False,
        source_preference="all"
    )
    client.end_conversation()


def demo_incognito_mode():
    """Demo 4: Incognito mode (no history saved)"""
    print("\n" + "="*70)
    print("DEMO 4: Incognito Mode (Private)")
    print("="*70)
    
    client = ConversationClient()
    
    # Incognito queries won't be saved
    client.chat(
        "What is quantum computing?",
        stream=False,
        is_incognito=True
    )
    
    client.chat(
        "How does it work?",
        stream=False,
        is_incognito=True
    )


def demo_streaming():
    """Demo 5: Streaming response"""
    print("\n" + "="*70)
    print("DEMO 5: Streaming Response")
    print("="*70)
    
    client = ConversationClient()
    client.start_conversation()
    
    client.chat(
        "Explain neural networks in detail",
        stream=True  # Enable streaming
    )
    
    client.end_conversation()


def demo_session_continuation():
    """Demo 6: Continue existing conversation"""
    print("\n" + "="*70)
    print("DEMO 6: Session Continuation")
    print("="*70)
    
    client = ConversationClient()
    
    # Start conversation
    conv_id = client.start_conversation()
    client.chat("What is AI?", stream=False)
    print(f"\n💾 Saving conversation ID: {conv_id}")
    
    # Simulate ending session
    client.end_conversation()
    
    print("\n⏳ Simulating app restart...")
    print("📂 Loading previous conversation...\n")
    
    # Continue with same conversation_id
    client.start_conversation(conversation_id=conv_id)
    client.chat(
        "Can you elaborate on that?",  # Should have context from previous
        stream=False
    )
    
    client.end_conversation()


def demo_api_compatibility():
    """Demo 7: Backwards compatibility with old API"""
    print("\n" + "="*70)
    print("DEMO 7: Backwards Compatibility (Old API Format)")
    print("="*70)
    
    # Old API format still works!
    old_payload = {
        "question": "What is machine learning?",  # Old: 'question'
        "stream": False  # Old: top-level 'stream'
    }
    
    print("📤 Using old API format:")
    print(json.dumps(old_payload, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/chat/basic",
        json=old_payload
    )
    
    result = response.json()
    print(f"\n🤖 Agent: {result['answer'][:100]}...")
    print("\n✅ Old API format still works!")


def interactive_mode():
    """Interactive conversation mode"""
    print("\n" + "="*70)
    print("🎮 INTERACTIVE MODE")
    print("="*70)
    print("Type your questions (or 'quit' to exit)")
    
    client = ConversationClient()
    client.start_conversation()
    
    while True:
        try:
            query = input("\n💬 You: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not query:
                continue
            
            # Check for special commands
            if query.startswith("/"):
                if query == "/incognito":
                    print("🕵️  Switched to incognito mode")
                    continue
                elif query == "/stream":
                    stream_mode = True
                    print("📡 Streaming enabled")
                    continue
                elif query.startswith("/lang "):
                    lang = query.split()[1]
                    print(f"🌐 Language set to {lang}")
                    continue
            
            client.chat(query, stream=False)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    client.end_conversation()


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║          OpenTA Agent - Session Management Demo                   ║
    ║                                                                    ║
    ║  This demo shows the new meta_params API structure and            ║
    ║  Redis-based session management for conversation history.         ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    
    # Check server
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✅ Server is running\n")
        else:
            print("⚠️  Server responded with non-200 status\n")
    except requests.exceptions.RequestException:
        print("❌ Error: Server is not running!")
        print("Please start the server first: python run.py\n")
        exit(1)
    
    # Demo menu
    demos = {
        "1": ("Basic Conversation", demo_basic_conversation),
        "2": ("Multilingual Support", demo_multilingual),
        "3": ("Source Preferences", demo_source_preferences),
        "4": ("Incognito Mode", demo_incognito_mode),
        "5": ("Streaming Response", demo_streaming),
        "6": ("Session Continuation", demo_session_continuation),
        "7": ("API Compatibility", demo_api_compatibility),
        "i": ("Interactive Mode", interactive_mode),
    }
    
    print("\n📋 Available Demos:")
    for key, (name, _) in demos.items():
        print(f"  {key}. {name}")
    print("  all. Run all demos (1-7)")
    print("  q. Quit")
    
    choice = input("\n👉 Select demo: ").strip().lower()
    
    if choice == 'q':
        print("Goodbye!")
        exit(0)
    elif choice == 'all':
        for key in ["1", "2", "3", "4", "5", "6", "7"]:
            demos[key][1]()
    elif choice in demos:
        demos[choice][1]()
    else:
        print("❌ Invalid choice!")
        exit(1)
    
    print("\n" + "="*70)
    print("✅ Demo completed!")
    print("="*70)
