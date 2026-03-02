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
    """Enhanced plan step with query strategy support.
    
    Allows AI planner to specify single vs multi-query retrieval
    without hardcoding heuristics.
    """
    id: int
    title: str
    description: str
    step_type: Literal["research", "synthesis", "comparison", "analysis"] = "research"
    query_strategy: Literal["single", "multi_query"] = "single"
    decomposition_hint: str | None = None
    focus_area: str | None = None
    
    # Legacy compatibility
    @property
    def needs_search(self) -> bool:
        return self.step_type in ("research", "comparison", "analysis")


# Legacy alias for backwards compatibility
PlanStep = SmartPlanStep


class ResearchPlanSignature(dspy.Signature):
    """
    Create a focused research plan with 2-3 smart steps.

    Rules:
    - General questions: 1 synthesis step, query_strategy='single'
    - Simple research: 1 research step + 1 synthesis step
    - Comparison queries: 2-3 steps with query_strategy='multi_query'
    - Use decomposition_hint to specify what to decompose (e.g., 'methods:A,B,C')
    - Keep steps minimal: 2-3 max, never exceed 4
    - Assign sequential integer ids starting from 0
    
    Step Types:
    - 'research': Investigate a topic (needs_search=True)
    - 'synthesis': Combine findings without new search (needs_search=False)
    - 'comparison': Compare multiple items (use multi_query strategy)
    - 'analysis': Analyze specific aspect (needs_search=True)
    
    Query Strategies:
    - 'single': One search query for this step
    - 'multi_query': Decompose into 2-4 parallel sub-queries
    
    Decomposition Hint Format:
    - 'methods:Random Forest,SVM,Neural Networks'
    - 'papers:P123,P456,P789'
    - 'aspects:accuracy,cost,privacy'
    """

    question: str = dspy.InputField(desc="The user's question")
    is_research: bool = dspy.InputField(
        desc="True if this question requires academic paper research"
    )
    steps: List[SmartPlanStep] = dspy.OutputField(
        desc="Ordered list of 2-3 smart plan steps with query strategies"
    )


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
        self, question: str, is_research: bool, cheap_lm=None
    ) -> List[PlanStep]:
        """
        Generate a research plan using the MAIN LLM (never cheap_lm).

        The planner must produce a well-formed nested JSON structure
        (List[SmartPlanStep]). Cheap/fast models often have low max_tokens
        and truncate mid-JSON, causing adapter parse failures.  We therefore
        always let the globally active (main) LM handle planning.

        `cheap_lm` is accepted here only for API compatibility; it is NOT
        used for the plan generation call itself.  It IS passed through to
        step_thinker calls in streaming.py.
        """
        try:
            # Always run with the main LM (no cheap_lm context here)
            result = self.planner(question=question, is_research=is_research)
            steps: List[PlanStep] = result.steps or []

            if not steps:
                logger.warning("[PLANNER] LM returned empty steps list — using default plan")
                return default_plan(is_research)

            # Guarantee sequential ids
            for i, step in enumerate(steps):
                step.id = i

            logger.info(
                "[PLANNER] Created plan with %d step(s): %s",
                len(steps),
                [s.title for s in steps],
            )
            return steps

        except Exception as e:
            logger.warning(
                "[PLANNER] Failed to generate plan (%s: %s) — falling back to default plan",
                type(e).__name__, e,
            )
            return default_plan(is_research)


def default_plan(is_research: bool) -> List[SmartPlanStep]:
    """Fallback plan when the planner module is unavailable."""
    if not is_research:
        return [
            SmartPlanStep(
                id=0,
                title="Preparing response",
                description="Formulate a helpful response to the general question",
                step_type="synthesis",
                query_strategy="single"
            )
        ]
    return [
        SmartPlanStep(
            id=0,
            title="Searching relevant papers",
            description="Find academic papers relevant to the question",
            step_type="research",
            query_strategy="single"
        ),
        SmartPlanStep(
            id=1,
            title="Synthesizing findings",
            description="Compile the retrieved information into a clear answer",
            step_type="synthesis",
            query_strategy="single"
        ),
    ]
