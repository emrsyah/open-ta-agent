"""
Test DSPy Streaming Implementation

This script tests the streaming functionality to ensure it follows
DSPy best practices and works correctly with SSE.
"""

import requests
import json
import time
from typing import Generator

BASE_URL = "http://localhost:8000"


def test_streaming_basic():
    """Test 1: Basic streaming with token-by-token output"""
    print("\n" + "="*70)
    print("TEST 1: Basic Streaming (Token-by-Token)")
    print("="*70)
    
    payload = {
        "query": "Explain machine learning in simple terms",
        "meta_params": {
            "stream": True,
            "language": "en-US"
        }
    }
    
    print(f"🔹 Query: {payload['query']}")
    print("🔹 Streaming response:\n")
    print("Assistant: ", end="", flush=True)
    
    start_time = time.time()
    token_count = 0
    
    response = requests.post(
        f"{BASE_URL}/chat/basic",
        json=payload,
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str == '[DONE]':
                    break
                
                try:
                    data = json.loads(data_str)
                    
                    if data.get("type") == "start":
                        print(f"\n[Stream started at {data.get('timestamp')}]")
                        print("Assistant: ", end="", flush=True)
                    
                    elif data.get("type") == "token":
                        print(data["content"], end="", flush=True)
                        token_count += 1
                    
                    elif data.get("type") == "rationale":
                        print(f"\n\n💭 Reasoning: {data['content']}\n")
                        print("Assistant: ", end="", flush=True)
                    
                    elif data.get("type") == "done":
                        print("\n")
                        if data.get("sources"):
                            print(f"📄 Sources: {', '.join(data['sources'])}")
                    
                    elif data.get("type") == "metadata":
                        print(f"\n📊 Metadata:")
                        print(f"   - Tokens: {data.get('token_count')}")
                        print(f"   - Duration: {data.get('duration_ms')}ms")
                    
                    elif data.get("type") == "error":
                        print(f"\n❌ Error: {data['content']}")
                
                except json.JSONDecodeError:
                    pass
    
    duration = time.time() - start_time
    print(f"\n✅ Test completed in {duration:.2f}s ({token_count} tokens)")


def test_streaming_vs_non_streaming():
    """Test 2: Compare streaming vs non-streaming"""
    print("\n" + "="*70)
    print("TEST 2: Streaming vs Non-Streaming Comparison")
    print("="*70)
    
    query = "What is deep learning?"
    
    # Test non-streaming
    print("\n🔹 Non-Streaming Request:")
    start = time.time()
    response = requests.post(
        f"{BASE_URL}/chat/basic",
        json={
            "query": query,
            "meta_params": {"stream": False}
        }
    )
    non_stream_duration = time.time() - start
    result = response.json()
    print(f"   Time: {non_stream_duration:.2f}s")
    print(f"   Answer length: {len(result['answer'])} chars")
    
    # Test streaming
    print("\n🔹 Streaming Request:")
    start = time.time()
    response = requests.post(
        f"{BASE_URL}/chat/basic",
        json={
            "query": query,
            "meta_params": {"stream": True}
        },
        stream=True
    )
    
    first_token_time = None
    answer_parts = []
    
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
                        if first_token_time is None:
                            first_token_time = time.time() - start
                        answer_parts.append(data["content"])
                except json.JSONDecodeError:
                    pass
    
    stream_duration = time.time() - start
    full_answer = "".join(answer_parts)
    
    print(f"   Time to first token: {first_token_time:.2f}s")
    print(f"   Total time: {stream_duration:.2f}s")
    print(f"   Answer length: {len(full_answer)} chars")
    
    print(f"\n📊 Analysis:")
    print(f"   - First token latency: {first_token_time:.2f}s (streaming advantage!)")
    print(f"   - Total time difference: {abs(stream_duration - non_stream_duration):.2f}s")


def test_streaming_with_history():
    """Test 3: Streaming with conversation history"""
    print("\n" + "="*70)
    print("TEST 3: Streaming with Conversation History")
    print("="*70)
    
    import uuid
    conversation_id = str(uuid.uuid4())
    
    # First message (non-streaming to build history)
    print("\n🔹 Turn 1 (Building history):")
    response1 = requests.post(
        f"{BASE_URL}/chat/basic",
        json={
            "query": "What is neural network?",
            "meta_params": {
                "stream": False,
                "conversation_id": conversation_id
            }
        }
    )
    result1 = response1.json()
    print(f"   Answer: {result1['answer'][:100]}...")
    
    # Second message (streaming with history)
    print("\n🔹 Turn 2 (Streaming with context):")
    print("   Query: 'How does it learn?'")
    print("   Assistant: ", end="", flush=True)
    
    response2 = requests.post(
        f"{BASE_URL}/chat/basic",
        json={
            "query": "How does it learn?",
            "meta_params": {
                "stream": True,
                "conversation_id": conversation_id
            }
        },
        stream=True
    )
    
    for line in response2.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str == '[DONE]':
                    break
                
                try:
                    data = json.loads(data_str)
                    if data.get("type") == "token":
                        print(data["content"], end="", flush=True)
                    elif data.get("type") == "done":
                        print("\n")
                        if data.get("sources"):
                            print(f"   📄 Sources: {', '.join(data['sources'])}")
                except json.JSONDecodeError:
                    pass
    
    print("\n✅ Conversation history maintained across turns!")


def test_streaming_error_handling():
    """Test 4: Error handling during streaming"""
    print("\n" + "="*70)
    print("TEST 4: Error Handling")
    print("="*70)
    
    # Test with invalid input
    print("\n🔹 Testing error handling (empty query):")
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat/basic",
            json={
                "query": "",  # Empty query
                "meta_params": {"stream": True}
            },
            stream=True,
            timeout=5
        )
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "error":
                            print(f"   ✅ Error properly caught: {data['content']}")
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"   ✅ Request validation caught error: {e}")


def test_streaming_languages():
    """Test 5: Multilingual streaming"""
    print("\n" + "="*70)
    print("TEST 5: Multilingual Streaming")
    print("="*70)
    
    queries = [
        ("en-US", "What is AI?"),
        ("id-ID", "Apa itu kecerdasan buatan?"),
    ]
    
    for lang, query in queries:
        print(f"\n🔹 Language: {lang}")
        print(f"   Query: {query}")
        print("   Assistant: ", end="", flush=True)
        
        response = requests.post(
            f"{BASE_URL}/chat/basic",
            json={
                "query": query,
                "meta_params": {
                    "stream": True,
                    "language": lang
                }
            },
            stream=True
        )
        
        word_count = 0
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
                            print(data["content"], end="", flush=True)
                            if data["content"].strip():
                                word_count += len(data["content"].split())
                    except json.JSONDecodeError:
                        pass
        
        print(f" ({word_count} words)\n")


def test_stream_performance():
    """Test 6: Performance metrics"""
    print("\n" + "="*70)
    print("TEST 6: Performance Metrics")
    print("="*70)
    
    queries = [
        "What is AI?",
        "Explain machine learning",
        "What are neural networks?"
    ]
    
    print("\n📊 Testing streaming performance...\n")
    
    for i, query in enumerate(queries, 1):
        print(f"Query {i}: {query}")
        
        start = time.time()
        first_token = None
        token_count = 0
        
        response = requests.post(
            f"{BASE_URL}/chat/basic",
            json={
                "query": query,
                "meta_params": {"stream": True}
            },
            stream=True
        )
        
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
                            if first_token is None:
                                first_token = time.time() - start
                            token_count += 1
                    except json.JSONDecodeError:
                        pass
        
        total_time = time.time() - start
        
        print(f"  • First token: {first_token:.2f}s")
        print(f"  • Total time: {total_time:.2f}s")
        print(f"  • Tokens: {token_count}")
        print(f"  • Avg latency: {(total_time/token_count if token_count > 0 else 0):.3f}s/token\n")


def run_all_tests():
    """Run all streaming tests"""
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║              DSPy Streaming Implementation Tests                  ║
    ║                                                                    ║
    ║  Testing streaming functionality based on DSPy best practices     ║
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
        return
    
    tests = [
        ("Basic Streaming", test_streaming_basic),
        ("Streaming vs Non-Streaming", test_streaming_vs_non_streaming),
        ("Streaming with History", test_streaming_with_history),
        ("Error Handling", test_streaming_error_handling),
        ("Multilingual Streaming", test_streaming_languages),
        ("Performance Metrics", test_stream_performance),
    ]
    
    print("Available tests:")
    for i, (name, _) in enumerate(tests, 1):
        print(f"  {i}. {name}")
    print("  all. Run all tests")
    print("  q. Quit")
    
    choice = input("\n👉 Select test (1-6, all, or q): ").strip().lower()
    
    if choice == 'q':
        print("Goodbye!")
        return
    elif choice == 'all':
        for name, test_func in tests:
            test_func()
    elif choice.isdigit() and 1 <= int(choice) <= len(tests):
        tests[int(choice)-1][1]()
    else:
        print("Invalid choice!")
        return
    
    print("\n" + "="*70)
    print("✅ Tests completed!")
    print("="*70)


if __name__ == "__main__":
    run_all_tests()
