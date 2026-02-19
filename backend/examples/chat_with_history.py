"""
Example: Using conversation history with OpenTA Agent

This script demonstrates how to have a multi-turn conversation
with the agent, maintaining context across turns.
"""

import requests
import json
from typing import List, Dict

BASE_URL = "http://localhost:8000"


class ConversationSession:
    """Manages a conversation session with history"""
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or "demo_session"
        self.history: List[Dict] = []
    
    def chat(self, question: str, stream: bool = False) -> Dict:
        """
        Send a question with conversation history
        
        Args:
            question: The question to ask
            stream: Whether to use streaming response
            
        Returns:
            Response dict with answer, sources, etc.
        """
        payload = {
            "question": question,
            "stream": stream,
            "session_id": self.session_id,
            "history": self.history
        }
        
        print(f"\n{'='*60}")
        print(f"Q: {question}")
        print(f"{'='*60}")
        
        response = requests.post(
            f"{BASE_URL}/chat/basic",
            json=payload
        )
        
        if not stream:
            result = response.json()
            print(f"A: {result['answer']}")
            if result.get('sources'):
                print(f"\n📄 Sources: {', '.join(result['sources'])}")
            if result.get('search_query'):
                print(f"🔍 Search Query: {result['search_query']}")
            
            # Add to history
            self.history.append({
                "question": question,
                "answer": result["answer"],
                "sources": result.get("sources", [])
            })
            
            return result
        else:
            # Handle streaming response
            print("A: ", end="", flush=True)
            answer_parts = []
            sources = []
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            break
                        
                        data = json.loads(data_str)
                        if data.get("type") == "token":
                            content = data["content"]
                            print(content, end="", flush=True)
                            answer_parts.append(content)
                        elif data.get("type") == "done":
                            sources = data.get("sources", [])
            
            print()  # New line after streaming
            if sources:
                print(f"\n📄 Sources: {', '.join(sources)}")
            
            # Add to history
            full_answer = "".join(answer_parts)
            self.history.append({
                "question": question,
                "answer": full_answer,
                "sources": sources
            })
            
            return {"answer": full_answer, "sources": sources}
    
    def clear_history(self):
        """Clear conversation history"""
        self.history = []
        print("\n🗑️  History cleared")
    
    def show_history(self):
        """Display current conversation history"""
        print(f"\n{'='*60}")
        print(f"CONVERSATION HISTORY ({len(self.history)} turns)")
        print(f"{'='*60}")
        for i, turn in enumerate(self.history, 1):
            print(f"\nTurn {i}:")
            print(f"  Q: {turn['question']}")
            print(f"  A: {turn['answer'][:100]}...")
            if turn.get('sources'):
                print(f"  Sources: {', '.join(turn['sources'])}")


def demo_basic_conversation():
    """Demo: Basic multi-turn conversation"""
    print("\n" + "="*60)
    print("DEMO 1: Basic Multi-Turn Conversation")
    print("="*60)
    
    session = ConversationSession()
    
    # Turn 1: Ask about a topic
    session.chat("What papers discuss machine learning in Telkom University?")
    
    # Turn 2: Follow-up question (uses pronoun referring to previous answer)
    session.chat("Which one is most recent?")
    
    # Turn 3: Ask for more details (agent knows context)
    session.chat("Can you tell me more about that one?")
    
    # Show history
    session.show_history()


def demo_streaming_conversation():
    """Demo: Streaming with history"""
    print("\n" + "="*60)
    print("DEMO 2: Streaming Conversation")
    print("="*60)
    
    session = ConversationSession(session_id="streaming_demo")
    
    # First question (non-streaming to build history)
    session.chat("What is deep learning?", stream=False)
    
    # Follow-up with streaming
    session.chat("What are the main applications?", stream=True)


def demo_research_session():
    """Demo: Multi-turn research session"""
    print("\n" + "="*60)
    print("DEMO 3: Research Session")
    print("="*60)
    
    session = ConversationSession(session_id="research_demo")
    
    # Exploring a research topic
    questions = [
        "What papers discuss neural networks?",
        "Which ones focus on computer vision?",
        "What techniques do they use?",
        "Are there any papers from 2024?",
        "Can you compare their approaches?"
    ]
    
    for question in questions:
        session.chat(question)
    
    session.show_history()


def demo_general_conversation():
    """Demo: Mix of general and research queries"""
    print("\n" + "="*60)
    print("DEMO 4: General + Research Conversation")
    print("="*60)
    
    session = ConversationSession(session_id="mixed_demo")
    
    # General greeting
    session.chat("Hello, who are you?")
    
    # Research question
    session.chat("Can you help me find papers about transformers?")
    
    # Follow-up
    session.chat("What are their key contributions?")
    
    # General question
    session.chat("Thanks! That's very helpful")


def demo_history_management():
    """Demo: Managing conversation history"""
    print("\n" + "="*60)
    print("DEMO 5: History Management")
    print("="*60)
    
    session = ConversationSession()
    
    # Build up some history
    session.chat("What is AI?")
    session.chat("What about ML?")
    session.chat("And deep learning?")
    
    # Show current history
    session.show_history()
    
    # Clear and start new topic
    session.clear_history()
    
    # New topic without previous context
    session.chat("Tell me about NLP research")


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║      OpenTA Agent - Conversation History Demo             ║
    ║                                                            ║
    ║  This script demonstrates multi-turn conversations        ║
    ║  with context maintained across questions.                ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✅ Server is running\n")
        else:
            print("⚠️  Server responded with non-200 status\n")
    except requests.exceptions.RequestException:
        print("❌ Error: Server is not running!")
        print("Please start the server first: python run.py\n")
        exit(1)
    
    # Run demos
    demos = [
        ("1", "Basic Conversation", demo_basic_conversation),
        ("2", "Streaming Conversation", demo_streaming_conversation),
        ("3", "Research Session", demo_research_session),
        ("4", "General + Research", demo_general_conversation),
        ("5", "History Management", demo_history_management),
    ]
    
    print("\nAvailable demos:")
    for num, name, _ in demos:
        print(f"  {num}. {name}")
    print("  all. Run all demos")
    print("  q. Quit")
    
    choice = input("\nSelect demo (1-5, all, or q): ").strip().lower()
    
    if choice == 'q':
        print("Goodbye!")
        exit(0)
    elif choice == 'all':
        for _, _, demo_func in demos:
            demo_func()
    elif choice in ['1', '2', '3', '4', '5']:
        demo_func = demos[int(choice) - 1][2]
        demo_func()
    else:
        print("Invalid choice!")
        exit(1)
    
    print("\n" + "="*60)
    print("Demo completed!")
    print("="*60)
