"""
LangGraph state definitions for the RAG pipeline.

This module defines the shared state (TypedDict) that flows through
all LangGraph nodes. Each node reads from and writes to this state.

The state mirrors the data previously managed ad-hoc in streaming.py,
but is now explicitly typed and centrally defined.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, List, Optional

from typing_extensions import TypedDict


class RAGGraphState(TypedDict, total=False):
    """Shared state flowing through the RAG LangGraph pipeline.

    Fields are marked total=False so nodes only need to return
    the keys they update.
    """

    # ── Input fields (set once at invocation) ──────────────────────────
    question: str
    conversation_id: Optional[str]
    history: Any  # dspy.History — kept as Any to avoid hard import at module level
    language: str
    source_preference: str
    is_incognito: bool
    user_id: Optional[str]
    
    # ── Filter fields for retrieval ─────────────────────────────────────
    catalog_type: Optional[str]
    year_from: Optional[int]
    year_to: Optional[int]
    author: Optional[str]
    has_electronic_access: Optional[bool]

    # ── Injected services (set by the service layer, read-only in nodes) ─
    cheap_lm: Any  # Optional cheap/fast LLM for lightweight calls
    retriever: Any  # PaperRetriever instance
    intent_classifier: Any  # DSPy IntentClassifier module
    query_generator: Any  # DSPy QueryGenerator module
    acknowledgment_generator: Any  # DSPy AcknowledgmentGenerator module
    planner: Any  # DSPy ResearchPlanner module
    query_reformulator: Any  # DSPy QueryReformulator module
    query_decomposer: Any  # DSPy QueryDecomposer module
    gap_detector: Any  # DSPy GapDetector module
    rag_module: Any  # DSPy PaperRAG module (ChainOfThought)

    # ── Intermediate results ───────────────────────────────────────────
    is_research: bool
    acknowledgment: Optional[str]
    pre_generated_query: Optional[str]

    # Planning
    plan_steps: list  # List[PlanStep] from planner
    current_step_idx: int

    # Retrieval (accumulated across steps)
    all_papers: Annotated[list, operator.add]
    all_context_parts: Annotated[list, operator.add]

    # ── Output fields ──────────────────────────────────────────────────
    final_answer: str
    final_sources: list  # List[CitedPaper dicts]
    cited_papers: list  # List[CitedPaper] objects for audit
    gap_verdict: str  # 'complete' or 'partial'
    title: Optional[str]

    # ── Callbacks (set by the service layer) ───────────────────────────
    on_complete: Any  # async callable(answer, sources, search_query)
    generate_title_fn: Any  # async callable(question, answer) -> str
    is_first_message: bool
    
    # ── Session context (for context-aware planning) ─────────────────────
    session_papers: list  # All papers retrieved in this conversation (from Redis/DB)
    last_answer: str  # Previous answer for follow-up context
    last_sources: list  # Previous sources for citation resolution
    needs_retrieval: bool  # Planner's decision on whether new retrieval is needed
