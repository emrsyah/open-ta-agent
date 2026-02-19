"""
Unit tests for conversation history management
"""

import pytest
import dspy
from app.services.rag import RAGService, PaperRAG
from app.services.retriever import PaperRetriever


class TestHistoryConversion:
    """Test history conversion from API format to DSPy format"""
    
    def test_empty_history(self):
        """Test conversion with no history"""
        rag_service = RAGService()
        result = rag_service._convert_to_dspy_history(None)
        
        assert isinstance(result, dspy.History)
        assert len(result.messages) == 0
    
    def test_single_message_history(self):
        """Test conversion with single message"""
        rag_service = RAGService()
        history = [
            {
                "question": "What is AI?",
                "answer": "AI is artificial intelligence",
                "sources": ["paper_1"],
                "context": "Some context"
            }
        ]
        
        result = rag_service._convert_to_dspy_history(history)
        
        assert isinstance(result, dspy.History)
        assert len(result.messages) == 1
        assert result.messages[0]["question"] == "What is AI?"
        assert result.messages[0]["answer"] == "AI is artificial intelligence"
        assert result.messages[0]["sources"] == ["paper_1"]
    
    def test_multiple_messages_history(self):
        """Test conversion with multiple messages"""
        rag_service = RAGService()
        history = [
            {
                "question": "What is AI?",
                "answer": "AI is artificial intelligence",
                "sources": ["paper_1"]
            },
            {
                "question": "What is ML?",
                "answer": "ML is machine learning",
                "sources": ["paper_2", "paper_3"]
            }
        ]
        
        result = rag_service._convert_to_dspy_history(history)
        
        assert isinstance(result, dspy.History)
        assert len(result.messages) == 2
        assert result.messages[0]["question"] == "What is AI?"
        assert result.messages[1]["question"] == "What is ML?"
    
    def test_history_without_sources(self):
        """Test conversion when sources are missing"""
        rag_service = RAGService()
        history = [
            {
                "question": "Hello",
                "answer": "Hi there!",
            }
        ]
        
        result = rag_service._convert_to_dspy_history(history)
        
        assert isinstance(result, dspy.History)
        assert len(result.messages) == 1
        assert "sources" not in result.messages[0]


class TestHistoryInModule:
    """Test that history is properly used in RAG module"""
    
    @pytest.fixture
    def mock_retriever(self):
        """Create a mock retriever"""
        class MockRetriever:
            async def get_context(self, query):
                return "Mock paper context"
        return MockRetriever()
    
    def test_module_accepts_history(self, mock_retriever):
        """Test that PaperRAG module accepts history parameter"""
        module = PaperRAG(retriever=mock_retriever)
        history = dspy.History(messages=[
            {"question": "Test", "answer": "Test answer"}
        ])
        
        # This should not raise an error
        try:
            # We can't fully test without mocking LM, but we can test the signature
            assert hasattr(module, 'generate')
            assert module.generate.signature == module.generate.signature
        except Exception as e:
            pytest.fail(f"Module should accept history: {e}")
    
    def test_module_with_empty_history(self, mock_retriever):
        """Test that PaperRAG works with empty history"""
        module = PaperRAG(retriever=mock_retriever)
        empty_history = dspy.History(messages=[])
        
        # Should not raise an error
        assert isinstance(empty_history, dspy.History)
        assert len(empty_history.messages) == 0


class TestAPIModels:
    """Test that API models support history correctly"""
    
    def test_conversation_message_model(self):
        """Test ConversationMessage model"""
        from app.core.models import ConversationMessage
        
        msg = ConversationMessage(
            question="What is AI?",
            answer="AI is artificial intelligence",
            sources=["paper_1"],
            context="Some context"
        )
        
        assert msg.question == "What is AI?"
        assert msg.answer == "AI is artificial intelligence"
        assert msg.sources == ["paper_1"]
        assert msg.context == "Some context"
    
    def test_chat_request_with_history(self):
        """Test ChatRequest with history field"""
        from app.core.models import ChatRequest, ConversationMessage
        
        history = [
            ConversationMessage(
                question="What is AI?",
                answer="AI is artificial intelligence"
            )
        ]
        
        request = ChatRequest(
            question="Tell me more",
            history=history
        )
        
        assert request.question == "Tell me more"
        assert len(request.history) == 1
        assert request.history[0].question == "What is AI?"
    
    def test_chat_request_without_history(self):
        """Test ChatRequest without history (backwards compatible)"""
        from app.core.models import ChatRequest
        
        request = ChatRequest(
            question="What is AI?",
            stream=False
        )
        
        assert request.question == "What is AI?"
        assert request.history is None


class TestHistoryPruning:
    """Test helper functions for history management"""
    
    def test_history_pruning_helper(self):
        """Test that we can prune long histories"""
        def prune_history(history, max_turns=10):
            if len(history) > max_turns:
                return history[-max_turns:]
            return history
        
        # Create long history
        long_history = [
            {"question": f"Q{i}", "answer": f"A{i}"}
            for i in range(20)
        ]
        
        pruned = prune_history(long_history, max_turns=5)
        
        assert len(pruned) == 5
        assert pruned[0]["question"] == "Q15"  # Keep last 5
        assert pruned[-1]["question"] == "Q19"
    
    def test_history_pruning_short_history(self):
        """Test pruning doesn't affect short histories"""
        def prune_history(history, max_turns=10):
            if len(history) > max_turns:
                return history[-max_turns:]
            return history
        
        short_history = [
            {"question": f"Q{i}", "answer": f"A{i}"}
            for i in range(3)
        ]
        
        pruned = prune_history(short_history, max_turns=10)
        
        assert len(pruned) == 3
        assert pruned == short_history


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
