"""
RAG (Retrieval-Augmented Generation) service using DSPy.
"""

import asyncio
import contextlib
import logging
import dspy
from typing import List, Optional
from app.services.retriever import PaperRetriever
from app.services.planner import ResearchPlanner
from app.core.models import CitedPaper

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
    You are 'OpenTA Agent', a specialized research assistant for Telkom University.

    Your behavior:
    - Maintain a professional, academic, yet friendly and helpful tone.
    - Consider conversation history to provide context-aware responses.
    - If context is provided, answer BASED ONLY on that context.
    - After every sentence or clause that uses information from a paper, append an inline citation like [1] or [1,2].
      The number corresponds to the paper's number in the context (Paper 1 → [1], Paper 2 → [2], etc.).
    - If no context/papers are relevant but the question is general, answer politely as a knowledgeable assistant without citations.
    - Use Indonesian for questions in Indonesian, and English for questions in English.
    - Reference previous conversation turns when appropriate.
    - Format the answer in Markdown (use headers, bullet points, bold where appropriate).
    """
    question: str = dspy.InputField(desc="User's current question about research papers")
    context: str = dspy.InputField(desc="Relevant paper abstracts and titles, numbered as Paper 1, Paper 2, etc.")
    history: dspy.History = dspy.InputField(desc="Previous conversation turns for context")
    answer: str = dspy.OutputField(desc="Markdown-formatted answer with inline citations [1], [2] after every sentence that references a paper")
    sources: List[str] = dspy.OutputField(desc="List of paper IDs actually cited in the answer, in citation order (e.g. the ID of Paper 1 first if [1] was used, then Paper 2's ID if [2] was used, etc.)")


class TitleGenerationSignature(dspy.Signature):
    """
    Generate a short, descriptive conversation title.
    The title should capture the core topic in 4-7 words.
    Do NOT use generic phrases like 'Research on' or 'Question about'.
    Return only the title text, no quotes or punctuation at the end.
    """
    question: str = dspy.InputField(desc="The user's first question")
    answer: str = dspy.InputField(desc="The assistant's first answer (summary)")
    title: str = dspy.OutputField(desc="Concise conversation title, 4-7 words")


class IntentClassificationSignature(dspy.Signature):
    """
    Categorize user input to decide if database research is needed.
    
    Categories:
    - 'research': Specific questions about papers, topics, authors, or research areas.
    - 'general': Greetings, identity ('who are you?'), general AI talk, or simple conversation.
    """
    question: str = dspy.InputField()
    category: str = dspy.OutputField(desc="'research' or 'general'")
    explanation: str = dspy.OutputField(desc="Brief reasoning for the chosen category")


class IntentClassifier(dspy.Module):
    """Classifies user intent to optimize retrieval paths."""
    def __init__(self):
        super().__init__()
        self.classify = dspy.Predict(IntentClassificationSignature)
        
    def forward(self, question: str) -> dspy.Prediction:
        return self.classify(question=question)


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
    
    def forward(self, question: str, context: str, history: Optional[dspy.History] = None) -> dspy.Prediction:
        """
        Process a question and generate an answer with conversation history.
        
        Args:
            question: User's question
            context: Pre-retrieved paper context string
            history: Conversation history for context-aware responses
            
        Returns:
            DSPy Prediction with answer and sources
        """
        # Use empty history if none provided
        if history is None:
            history = dspy.History(messages=[])
        
        # Generate answer with reasoning and history context
        result = self.generate(
            question=question,
            context=context,
            history=history
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
        self.intent_classifier = IntentClassifier()
        self.planner = ResearchPlanner()
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
    
    def _build_cited_papers(
        self,
        source_ids: List[str],
        retrieved_papers: list
    ) -> List[CitedPaper]:
        """
        Match DSPy-returned source IDs against already-retrieved papers to build
        CitedPaper objects without extra DB calls.
        Citation number is the 1-based position in the sources list.
        """
        paper_map = {p.id: p for p in retrieved_papers}
        cited = []
        seen = set()
        for i, pid in enumerate(source_ids, 1):
            if pid in seen:
                continue
            seen.add(pid)
            paper = paper_map.get(pid)
            if paper:
                cited.append(CitedPaper(
                    id=paper.id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                    year=paper.year,
                    citation_number=i,
                ))
        return cited

    def _convert_to_dspy_history(self, history_messages: Optional[List[dict]]) -> dspy.History:
        """
        Convert conversation history from request model to dspy.History.
        
        Args:
            history_messages: List of conversation messages from ChatRequest
            
        Returns:
            dspy.History object with converted messages
        """
        if not history_messages:
            return dspy.History(messages=[])
        
        dspy_messages = []
        for msg in history_messages:
            # Convert each message to the format expected by dspy.History
            history_entry = {
                "question": msg.get("question", ""),
                "answer": msg.get("answer", ""),
                "context": msg.get("context", ""),
            }
            # Include sources if available
            if msg.get("sources"):
                history_entry["sources"] = msg.get("sources")
            
            dspy_messages.append(history_entry)
        
        return dspy.History(messages=dspy_messages)
    
    async def chat(
        self, 
        question: str, 
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all"
    ) -> dict:
        """
        Get answer for a question with conversation history support (non-streaming).
        
        Args:
            question: User question
            history: Optional list of previous conversation messages
            language: User's preferred language (e.g., 'id-ID', 'en-US')
            source_preference: Filter for sources ('all', 'only_papers', 'only_general')
            
        Returns:
            Dict with answer, sources, and optional rationale
        """
        logger.info(f"[RAG] Processing question: '{question}'")
        if history:
            logger.info(f"[RAG] Using conversation history with {len(history)} previous turns")
        
        # Convert history to dspy.History format
        dspy_history = self._convert_to_dspy_history(history)
        
        # Step 0: Classify intent
        logger.info("[RAG] Classifying intent...")
        if self.cheap_lm:
            with dspy.context(lm=self.cheap_lm):
                intent_res = self.intent_classifier(question=question)
        else:
            intent_res = self.intent_classifier(question=question)
            
        logger.info(f"[RAG] Intent classified: {intent_res.category} ({intent_res.explanation})")
        
        if intent_res.category == "general":
            logger.info("[RAG] General intent detected. Skipping retrieval.")
            result = self.rag_module(
                question=question,
                context="No paper context needed for this general query.",
                history=dspy_history
            )
            return {
                "answer": result.answer,
                "sources": [],
                "rationale": getattr(result, 'rationale', None),
                "search_query": None
            }

        # Step 1: Generate optimized search query using LLM
        search_query = self._generate_search_query(question)

        # Step 2: Retrieve context + papers together (avoids extra DB calls later)
        logger.info(f"[RAG] Retrieving context with query: '{search_query}'")
        context, retrieved_papers = await self.retriever.get_papers_with_context(search_query)
        logger.info(f"[RAG] Context retrieved (length: {len(context)} chars, {len(retrieved_papers)} papers)")

        # Step 3: Generate answer with history context
        logger.info("[RAG] Generating answer with DSPy and conversation history...")
        result = self.rag_module(
            question=question,
            context=context,
            history=dspy_history
        )

        cited_papers = self._build_cited_papers(
            getattr(result, 'sources', []),
            retrieved_papers
        )

        logger.info(f"[RAG] Answer generated ({len(result.answer)} chars, {len(cited_papers)} cited papers)")

        return {
            "answer": result.answer,
            "sources": cited_papers,
            "rationale": getattr(result, 'rationale', None),
            "search_query": search_query
        }
    
    async def generate_title(self, question: str, answer: str) -> str:
        """
        Generate a short conversation title from the first Q&A turn.
        Uses cheap_lm to keep cost and latency low.
        Falls back to truncated question if LLM call fails.
        """
        try:
            predictor = dspy.Predict(TitleGenerationSignature)
            ctx = dspy.context(lm=self.cheap_lm) if self.cheap_lm else contextlib.nullcontext()
            with ctx:
                result = await asyncio.to_thread(
                    predictor,
                    question=question,
                    answer=answer[:500],  # truncate long answers
                )
            title = result.title.strip().strip('"').strip("'")
            logger.info("[RAG] Generated title: '%s'", title)
            return title
        except Exception as e:
            logger.warning("[RAG] Title generation failed: %s", e)
            q = question.strip()
            return q[:60].rsplit(" ", 1)[0] + "…" if len(q) > 60 else q

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
