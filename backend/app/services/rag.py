"""
RAG (Retrieval-Augmented Generation) service using DSPy.
"""

import logging
import dspy
from typing import List, Optional
from app.services.retriever import PaperRetriever

logger = logging.getLogger(__name__)


class QueryGenerationSignature(dspy.Signature):
    """
    Generate optimal search keywords from user questions.
    
    Convert conversational questions into database-friendly search terms.
    Extract the core concepts and technical keywords that would appear in paper titles and abstracts.
    """
    user_question: str = dspy.InputField(desc="The user's original question in natural language")
    search_query: str = dspy.OutputField(desc="Optimized search keywords (3-5 key terms) for database lookup")


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


class QueryGenerator(dspy.Module):
    """
    Generates optimized search queries from user questions.
    
    Uses LLM to extract keywords and convert conversational queries
    into database-friendly search terms.
    """
    
    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(QueryGenerationSignature)
    
    def forward(self, user_question: str) -> dspy.Prediction:
        """
        Generate search keywords from user question.
        
        Args:
            user_question: The user's natural language question
            
        Returns:
            Prediction with optimized search_query
        """
        result = self.generate(user_question=user_question)
        return dspy.Prediction(
            search_query=result.search_query,
            rationale=getattr(result, 'rationale', None)
        )


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
    
    def forward(self, question: str, context: str) -> dspy.Prediction:
        """
        Process a question and generate an answer.
        
        Args:
            question: User's question
            context: Pre-retrieved paper context string
            
        Returns:
            DSPy Prediction with answer and sources
        """
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
    Uses a cheap model for query generation and main model for answer generation.
    """
    
    def __init__(self, retriever: PaperRetriever | None = None, cheap_lm=None):
        """
        Initialize RAG service.
        
        Args:
            retriever: PaperRetriever instance, or None to create default
            cheap_lm: Cheap/fast model for query generation (optional)
        """
        self.retriever = retriever or PaperRetriever()
        self.rag_module = PaperRAG(retriever=self.retriever)
        self.query_generator = QueryGenerator()
        self.cheap_lm = cheap_lm
    
    def _generate_search_query(self, user_question: str) -> str:
        """
        Use LLM to generate optimized search keywords.
        Uses cheap model if available to save costs.
        
        Args:
            user_question: The user's original question
            
        Returns:
            Optimized search query string
        """
        logger.info(f"[RAG] Generating search query from: '{user_question}'")
        
        if self.cheap_lm:
            # Use cheap model for query generation
            logger.debug("[RAG] Using cheap model for query generation")
            with dspy.context(lm=self.cheap_lm):
                result = self.query_generator(user_question=user_question)
        else:
            # Fallback to default model
            result = self.query_generator(user_question=user_question)
        
        search_query = result.search_query
        logger.info(f"[RAG] Generated search query: '{search_query}'")
        logger.debug(f"[RAG] Query generation rationale: {getattr(result, 'rationale', 'N/A')}")
        return search_query
    
    async def chat(self, question: str) -> dict:
        """
        Get answer for a question (non-streaming).
        
        Args:
            question: User question
            
        Returns:
            Dict with answer, sources, and optional rationale
        """
        logger.info(f"[RAG] Processing question: '{question}'")
        
        # Step 1: Generate optimized search query using LLM
        search_query = self._generate_search_query(question)
        
        # Step 2: Retrieve context using the generated query
        logger.info(f"[RAG] Retrieving context with query: '{search_query}'")
        context = await self.retriever.get_context(search_query)
        logger.info(f"[RAG] Context retrieved (length: {len(context)} chars)")
        logger.debug(f"[RAG] Context content: {context[:300]}...")
        
        # Step 3: Generate answer (sync DSPy module)
        logger.info("[RAG] Generating answer with DSPy...")
        result = self.rag_module(question=question, context=context)
        
        logger.info(f"[RAG] Answer generated (length: {len(result.answer)} chars, sources: {result.sources})")
        
        return {
            "answer": result.answer,
            "sources": result.sources,
            "rationale": getattr(result, 'rationale', None),
            "search_query": search_query  # Include for transparency
        }
    
    def get_module(self) -> PaperRAG:
        """Get the RAG module for streaming."""
        return self.rag_module
    
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


def init_rag_service(retriever: PaperRetriever | None = None, cheap_lm=None) -> RAGService:
    """
    Initialize the global RAG service.
    
    Args:
        retriever: Optional custom retriever
        cheap_lm: Optional cheap model for query generation
        
    Returns:
        The initialized RAGService
    """
    global _rag_service
    _rag_service = RAGService(retriever=retriever, cheap_lm=cheap_lm)
    return _rag_service
