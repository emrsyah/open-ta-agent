"""
Research planning module using DSPy.

Generates a variable-length step-by-step plan before RAG execution,
enabling a Manus-like "thinking process" UX.
"""

from __future__ import annotations

import contextlib
import logging
from typing import List

import dspy
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    id: int
    title: str
    description: str
    needs_search: bool


class ResearchPlanSignature(dspy.Signature):
    """
    Create a focused, minimal research plan to answer the user's question.

    Rules:
    - General questions (greetings, identity, small talk): 1 step, needs_search=false.
    - Simple single-topic research: 2 steps (one search step, one synthesis step).
    - Complex or multi-faceted research questions: 3-4 steps, never exceed 4.
    - Step titles must be short action phrases (3-6 words, e.g. "Search relevant papers").
    - Set needs_search=true only on steps that require retrieving academic papers.
    - Assign sequential integer ids starting from 0.
    """

    question: str = dspy.InputField(desc="The user's question")
    is_research: bool = dspy.InputField(
        desc="True if this question requires academic paper research"
    )
    steps: List[PlanStep] = dspy.OutputField(
        desc="Ordered list of 1-4 plan steps"
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
        ctx = dspy.context(lm=cheap_lm) if cheap_lm else contextlib.nullcontext()
        with ctx:
            result = self.planner(question=question, is_research=is_research)

        steps: List[PlanStep] = result.steps or []
        # Guarantee sequential ids
        for i, step in enumerate(steps):
            step.id = i

        logger.info(
            "[PLANNER] Created plan with %d step(s): %s",
            len(steps),
            [s.title for s in steps],
        )
        return steps


def default_plan(is_research: bool) -> List[PlanStep]:
    """Fallback plan when the planner module is unavailable."""
    if not is_research:
        return [
            PlanStep(
                id=0,
                title="Preparing response",
                description="Formulate a helpful response to the general question",
                needs_search=False,
            )
        ]
    return [
        PlanStep(
            id=0,
            title="Searching relevant papers",
            description="Find academic papers relevant to the question",
            needs_search=True,
        ),
        PlanStep(
            id=1,
            title="Synthesizing findings",
            description="Compile the retrieved information into a clear answer",
            needs_search=False,
        ),
    ]
