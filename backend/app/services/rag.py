"""
RAG (Retrieval-Augmented Generation) service using DSPy.
"""

import dspy
from typing import List, Optional
from app.services.retriever import PaperRetriever


class PaperChatSignature(dspy.Signature):
    """
    Signature for paper Q&A with citations.
    
    Input: question and context (retrieved papers)
    Output: answer with cited sources
    """
    question: str = dspy.InputField(desc="User's question about research papers")
    context: str = dspy.InputField(desc="Relevant paper abstracts and titles")
    answer: str = dspy.OutputField(desc="Comprehensive answer with citations")
    sources: List[str] = dspy.OutputField(desc="List of paper IDs referenced")


class PaperRAG(dspy.Module):
    """
    RAG module for paper Q&A.
    
    Architecture:
    1. Retrieve relevant papers using PaperRetriever
    2. Generate answer using Chain of Thought reasoning
    3. Return answer with source citations
    """
    
    def __init__(self, retriever: PaperRetriever):
        """
        Initialize RAG module.
        
        Args:
            retriever: PaperRetriever instance for finding relevant papers
        """
        super().__init__()
        self.retriever = retriever
        self.generate = dspy.ChainOfThought(PaperChatSignature)
    
    def forward(self, question: str) -> dspy.Prediction:
        """
        Process a question and generate an answer.
        
        Args:
            question: User's question
            
        Returns:
            DSPy Prediction with answer and sources
        """
        # Retrieve relevant papers
        context = self.retriever.get_context(question)
        
        # Generate answer with reasoning
        result = self.generate(
            question=question,
            context=context
        )
        
        return dspy.Prediction(
            answer=result.answer,
            sources=result.sources,
            rationale=getattr(result, 'rationale', None)
        )


class RAGService:
    """
    Service layer for RAG operations.
    
    Handles initialization of DSPy modules and provides async interface.
    """
    
    def __init__(self, retriever: PaperRetriever | None = None):
        """
        Initialize RAG service.
        
        Args:
            retriever: PaperRetriever instance, or None to create default
        """
        self.retriever = retriever or PaperRetriever()
        self.rag_module = PaperRAG(retriever=self.retriever)
        # Create async version
        self.rag_async = dspy.asyncify(self.rag_module)
    
    async def chat(self, question: str) -> dict:
        """
        Get answer for a question (non-streaming).
        
        Args:
            question: User question
            
        Returns:
            Dict with answer, sources, and optional rationale
        """
        result = await self.rag_async(question=question)
        
        return {
            "answer": result.answer,
            "sources": result.sources,
            "rationale": getattr(result, 'rationale', None)
        }
    
    def get_module(self) -> dspy.Module:
        """Get the async RAG module for streaming."""
        return self.rag_async
    
    def get_retriever(self) -> PaperRetriever:
        """Get the paper retriever."""
        return self.retriever


# Global instance (initialized on startup)
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Get or create the global RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def init_rag_service(retriever: PaperRetriever | None = None) -> RAGService:
    """
    Initialize the global RAG service.
    
    Args:
        retriever: Optional custom retriever
        
    Returns:
        The initialized RAGService
    """
    global _rag_service
    _rag_service = RAGService(retriever=retriever)
    return _rag_service
