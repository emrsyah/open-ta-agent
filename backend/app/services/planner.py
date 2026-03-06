"""
Research planning module using DSPy.

Generates a variable-length step-by-step plan before RAG execution,
enabling a Manus-like "thinking process" UX.
"""

from __future__ import annotations

import contextlib
import logging
from typing import List, Literal, Optional

import dspy
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SmartPlanStep(BaseModel):
    """Enhanced plan step with context-aware action support.
    
    Allows AI planner to specify:
    - Whether to retrieve new papers or use existing ones
    - Which cited papers ([1], [2], etc.) to use
    - What action type to perform (search, compare, analyze, clarify, etc.)
    """
    id: int
    title: str
    description: str
    
    # Action type determines what this step does
    action_type: Literal[
        "search",        # Retrieve new papers from database
        "compare",       # Compare cited papers (no new retrieval)
        "summarize",     # Summarize cited papers (no new retrieval)
        "analyze",       # Analyze patterns across cited papers (no new retrieval)
        "extract",       # Extract specific info from cited papers (no new retrieval)
        "clarify",       # Clarify/re-explain previous answer (no retrieval)
        "deep_dive",     # Fetch full PDF of cited paper for detailed analysis
        "synthesis",     # Combine findings without new search
        "research",      # Legacy: general research with search
    ] = "research"
    
    # Which papers to use for contextual actions (e.g., [1, 2] for "compare [1] and [2]")
    use_cited_papers: List[int] = []  # Paper numbers like [1], [2] -> stored as [1, 2]
    
    # Query strategy for search actions
    query_strategy: Literal["single", "multi_query"] = "single"
    decomposition_hint: str | None = None
    focus_area: str | None = None
    
    @property
    def needs_search(self) -> bool:
        """Returns True if this step requires new paper retrieval."""
        return self.action_type in ("search", "research", "deep_dive")
    
    @property
    def is_contextual(self) -> bool:
        """Returns True if this step uses existing papers without retrieval."""
        return self.action_type in ("compare", "summarize", "analyze", "extract", "clarify")


# Legacy aliases for backwards compatibility
PlanStep = SmartPlanStep

class ResearchPlanSignature(dspy.Signature):
    """
    Create a context-aware research plan.
    
    IMPORTANT: Analyze the session context first!
    
    Context Analysis Rules:
    1. If user references papers like [1], [2], "the first paper", "paper 3" - use those papers, don't search
    2. If user asks to compare, summarize, or analyze existing papers - use action_type accordingly
    3. If user asks to clarify or explain previous answer differently - use clarify action
    4. Only use 'search' action when truly new papers are needed
    
    Action Types:
    - 'search': Retrieve new papers from database (needs_search=True)
    - 'compare': Compare papers specified in use_cited_papers (needs_search=False)
    - 'summarize': Summarize papers in use_cited_papers (needs_search=False)
    - 'analyze': Find patterns/themes across papers (needs_search=False)
    - 'extract': Extract specific info (methodology, authors, etc.) from papers (needs_search=False)
    - 'clarify': Re-explain previous answer differently (needs_search=False)
    - 'deep_dive': Fetch full PDF for detailed analysis (needs_search=True)
    - 'synthesis': Combine findings without new search (needs_search=False)
    - 'research': Legacy general research (needs_search=True)
    
    use_cited_papers: List of paper numbers (1-indexed) to use. Examples:
    - "Compare [1] and [2]" -> use_cited_papers=[1, 2], action_type="compare"
    - "Summarize the first paper" -> use_cited_papers=[1], action_type="summarize"
    - "What's the methodology of [3]?" -> use_cited_papers=[3], action_type="extract"
    
    Keep plans minimal: 1-2 steps for contextual actions, 2-3 for research.
    """

    # Inputs
    question: str = dspy.InputField(desc="The user's question")
    is_research: bool = dspy.InputField(desc="True if this question requires academic paper research")
    session_papers: str = dspy.InputField(desc="JSON list of papers already retrieved in this conversation with their titles, IDs, and citation numbers. Empty string if no papers yet.")
    last_answer: str = dspy.InputField(desc="Previous answer from the conversation. Empty string if first message.")
    
    # Outputs
    needs_retrieval: bool = dspy.OutputField(desc="True if new papers need to be retrieved, False if using existing papers")
    steps: List[SmartPlanStep] = dspy.OutputField(desc="Ordered list of 1-3 plan steps with action types")


# Legacy alias
ContextAwarePlanSignature = ResearchPlanSignature

class StepThinkingSignature(dspy.Signature):
    """
    Think through one step of a research plan. Be concise (2-4 sentences).
    Focus only on what this specific step involves.
    Do NOT write the final answer here — that comes later.
    """

    question: str = dspy.InputField(desc="The original user question")
    step_title: str = dspy.InputField(desc="Title of the current step")
    step_description: str = dspy.InputField(
        desc="What this step should accomplish"
    )
    gathered_context: str = dspy.InputField(
        desc="Summary of information gathered in previous steps"
    )
    thinking: str = dspy.OutputField(
        desc="Concise reasoning for this step (2-4 sentences, no final answer)"
    )


class ResearchPlanner(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.planner = dspy.Predict(ResearchPlanSignature)
        self.step_thinker = dspy.Predict(StepThinkingSignature)

    def create_plan(
        self,
        question: str,
        is_research: bool,
        session_papers: List[dict] | None = None,
        last_answer: str = "",
        cheap_lm=None,
    ) -> tuple[bool, List[PlanStep]]:
        """
        Generate a context-aware research plan.
        
        Returns:
            tuple of (needs_retrieval: bool, steps: List[PlanStep])
        
        The planner analyzes session context to decide:
        - Whether new papers need to be retrieved
        - Which existing papers to use (via use_cited_papers)
        - What action type to perform (compare, summarize, etc.)
        
        Args:
            question: User's question
            is_research: Whether this is a research question
            session_papers: List of papers already retrieved in this conversation
                           Each dict should have: id, title, citation_number
            last_answer: Previous answer for context
            cheap_lm: Accepted for API compatibility but NOT used for planning
        """
        # Format session papers for the planner
        import json
        papers_json = ""
        if session_papers:
            papers_json = json.dumps([
                {
                    "citation_number": p.get("citation_number", i + 1),
                    "id": p.get("id"),
                    "title": p.get("title", "Unknown"),
                }
                for i, p in enumerate(session_papers)
            ])
        
        try:
            result = self.planner(
                question=question,
                is_research=is_research,
                session_papers=papers_json,
                last_answer=last_answer[:1000] if last_answer else "",  # Truncate to avoid token bloat
            )
            
            needs_retrieval = getattr(result, "needs_retrieval", True)
            steps: List[PlanStep] = result.steps or []

            if not steps:
                logger.warning("[PLANNER] LM returned empty steps list — using default plan")
                return True, default_plan(is_research)

            # Guarantee sequential ids
            for i, step in enumerate(steps):
                step.id = i

            logger.info(
                "[PLANNER] Created plan with %d step(s), needs_retrieval=%s: %s",
                len(steps),
                needs_retrieval,
                [(s.title, s.action_type) for s in steps],
            )
            return needs_retrieval, steps

        except Exception as e:
            logger.warning(
                "[PLANNER] Failed to generate plan (%s: %s) — falling back to default plan",
                type(e).__name__, e,
            )
            return True, default_plan(is_research)

def default_plan(is_research: bool, contextual: bool = False) -> List[SmartPlanStep]:
    """Fallback plan when the planner module is unavailable.
    
    Args:
        is_research: Whether this is a research question
        contextual: If True, create a plan for contextual follow-up (no retrieval)
    """
    if contextual:
        return [
            SmartPlanStep(
                id=0,
                title="Analyzing existing papers",
                description="Work with papers from our conversation",
                action_type="synthesis",
                use_cited_papers=[],
                query_strategy="single"
            )
        ]
    
    if not is_research:
        return [
            SmartPlanStep(
                id=0,
                title="Preparing response",
                description="Formulate a helpful response to the general question",
                action_type="synthesis",
                query_strategy="single"
            )
        ]
    
    return [
        SmartPlanStep(
            id=0,
            title="Searching relevant papers",
            description="Find academic papers relevant to the question",
            action_type="search",
            query_strategy="single"
        ),
        SmartPlanStep(
            id=1,
            title="Synthesizing findings",
            description="Compile the retrieved information into a clear answer",
            action_type="synthesis",
            query_strategy="single"
        ),
    ]
