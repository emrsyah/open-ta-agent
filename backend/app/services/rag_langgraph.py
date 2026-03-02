"""
LangGraph-based RAG service.

Wraps the LangGraph pipeline into a service class that mirrors
the interface of the original RAGService for easy integration
into the chat route.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, AsyncGenerator, List, Optional

import dspy

from app.services.retriever import PaperRetriever
from app.services.planner import ResearchPlanner
from app.services.query_decomposer import QueryDecomposer
from app.services.graph_builder import build_rag_graph
from app.services.graph_state import RAGGraphState

# Re-use DSPy modules from original rag.py
from app.services.rag import (
    IntentClassifier,
    QueryGenerator,
    QueryReformulator,
    AcknowledgmentGenerator,
    GapDetector,
    PaperRAG,
    TitleGenerationSignature,
)

logger = logging.getLogger(__name__)


class RAGServiceLangGraph:
    """RAG service powered by LangGraph + DSPy.

    Uses LangGraph as the orchestration layer while keeping
    all DSPy modules intact for prompt optimization.
    """

    def __init__(self, retriever: PaperRetriever | None = None, cheap_lm=None):
        self.retriever = retriever or PaperRetriever()
        self.cheap_lm = cheap_lm

        # Re-use all existing DSPy modules
        self.rag_module = PaperRAG(retriever=self.retriever)
        self.query_generator = QueryGenerator()
        self.query_reformulator = QueryReformulator()
        self.query_decomposer = QueryDecomposer()
        self.intent_classifier = IntentClassifier()
        self.acknowledgment_generator = AcknowledgmentGenerator()
        self.planner = ResearchPlanner()
        self.gap_detector = GapDetector()

        # Build the LangGraph
        self.graph = build_rag_graph()

        logger.info("[RAG-LG] LangGraph RAG service initialized")

    def _convert_to_dspy_history(self, history_messages: Optional[List[dict]]) -> dspy.History:
        """Convert conversation history to dspy.History (same as original RAGService)."""
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

    def _build_initial_state(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all",
        conversation_id: Optional[str] = None,
        is_incognito: bool = False,
        user_id: Optional[str] = None,
        on_complete: Any = None,
        generate_title_fn: Any = None,
        is_first_message: bool = False,
    ) -> RAGGraphState:
        """Build the initial state dict for the LangGraph invocation."""
        dspy_history = self._convert_to_dspy_history(history)

        return {
            # Input
            "question": question,
            "conversation_id": conversation_id,
            "history": dspy_history,
            "language": language,
            "source_preference": source_preference,
            "is_incognito": is_incognito,
            "user_id": user_id,
            # Services (injected into state for nodes to use)
            "cheap_lm": self.cheap_lm,
            "retriever": self.retriever,
            "intent_classifier": self.intent_classifier,
            "query_generator": self.query_generator,
            "acknowledgment_generator": self.acknowledgment_generator,
            "planner": self.planner,
            "query_reformulator": self.query_reformulator,
            "query_decomposer": self.query_decomposer,
            "gap_detector": self.gap_detector,
            "rag_module": self.rag_module,
            # Intermediate
            "is_research": False,
            "pre_generated_query": None,
            "plan_steps": [],
            "current_step_idx": 0,
            "all_papers": [],
            "all_context_parts": [],
            # Output
            "final_answer": "",
            "final_sources": [],
            "cited_papers": [],
            "gap_verdict": "complete",
            "title": None,
            # Callbacks
            "on_complete": on_complete,
            "generate_title_fn": generate_title_fn,
            "is_first_message": is_first_message,
        }

    async def chat(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all",
    ) -> dict:
        """Non-streaming chat (mirrors original RAGService.chat)."""
        state = self._build_initial_state(
            question=question,
            history=history,
            language=language,
            source_preference=source_preference,
        )

        result = await self.graph.ainvoke(state)

        return {
            "answer": result.get("final_answer", ""),
            "sources": result.get("final_sources", []),
            "rationale": None,
            "search_query": result.get("pre_generated_query"),
        }

    async def stream_response(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all",
        conversation_id: Optional[str] = None,
        is_incognito: bool = False,
        user_id: Optional[str] = None,
        on_complete: Any = None,
        generate_title_fn: Any = None,
        is_first_message: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream LangGraph response as SSE events.

        Uses stream_mode='custom' to capture events emitted by
        get_stream_writer() inside each node.
        """
        from app.utils.streaming import format_sse

        state = self._build_initial_state(
            question=question,
            history=history,
            language=language,
            source_preference=source_preference,
            conversation_id=conversation_id,
            is_incognito=is_incognito,
            user_id=user_id,
            on_complete=on_complete,
            generate_title_fn=generate_title_fn,
            is_first_message=is_first_message,
        )

        try:
            async for event in self.graph.astream(
                state,
                stream_mode="custom",
            ):
                # Each event is a dict emitted by get_stream_writer() in nodes
                if isinstance(event, dict):
                    event_type = event.get("type", "")

                    # Skip internal keepalive markers — emit SSE keepalive instead
                    if event_type == "_keepalive":
                        yield ": keepalive\n\n"
                        continue

                    yield format_sse(event)

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("[RAG-LG] Stream error: %s", e, exc_info=True)
            yield format_sse({"type": "error", "content": str(e)})
            yield "data: [DONE]\n\n"

    async def generate_title(self, question: str, answer: str) -> str:
        """Generate conversation title (same as original RAGService)."""
        try:
            predictor = dspy.Predict(TitleGenerationSignature)
            ctx = dspy.context(lm=self.cheap_lm) if self.cheap_lm else contextlib.nullcontext()
            with ctx:
                result = await asyncio.to_thread(
                    predictor,
                    question=question,
                    answer=answer[:500],
                )
            title = result.title.strip().strip('"').strip("'")
            logger.info("[RAG-LG] Generated title: '%s'", title)
            return title
        except Exception as e:
            logger.warning("[RAG-LG] Title generation failed: %s", e)
            q = question.strip()
            return q[:60].rsplit(" ", 1)[0] + "…" if len(q) > 60 else q


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_rag_service_lg: RAGServiceLangGraph | None = None


def get_rag_service_lg() -> RAGServiceLangGraph:
    """Get or create the global LangGraph RAG service instance."""
    global _rag_service_lg
    if _rag_service_lg is None:
        _rag_service_lg = RAGServiceLangGraph()
    return _rag_service_lg


def init_rag_service_lg(
    retriever: PaperRetriever | None = None, cheap_lm=None
) -> RAGServiceLangGraph:
    """Initialize the global LangGraph RAG service."""
    global _rag_service_lg
    _rag_service_lg = RAGServiceLangGraph(retriever=retriever, cheap_lm=cheap_lm)
    return _rag_service_lg
