"""
LangGraph node functions for the RAG pipeline.

Each node wraps one or more existing DSPy modules and uses
get_stream_writer() to emit SSE-compatible events to the client.
The nodes read from / write to the shared RAGGraphState.

All DSPy modules are **re-used** — imported from their original locations.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Literal

import dspy
from langgraph.config import get_stream_writer
from langgraph.types import Command

from app.services.graph_state import RAGGraphState
from app.utils.streaming import (
    _build_cited_papers,
    _audit_citations,
    _should_use_default_plan,
)
from app.services.planner import default_plan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (re-used from streaming.py patterns)
# ---------------------------------------------------------------------------

async def _run_dspy_sync(fn, cheap_lm=None, **kwargs):
    """Run a blocking DSPy call in a thread pool."""
    def _call():
        ctx = dspy.context(lm=cheap_lm) if cheap_lm else contextlib.nullcontext()
        with ctx:
            return fn(**kwargs)
    return await asyncio.to_thread(_call)


def _paper_summary(papers: list) -> str:
    if not papers:
        return "No papers retrieved yet."
    lines = ["Retrieved papers:"]
    for i, p in enumerate(papers, 1):
        lines.append(f"  {i}. {p.title} ({p.year})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node: classify_intent
# ---------------------------------------------------------------------------

async def classify_intent(state: RAGGraphState) -> Command[Literal[
    "acknowledge", "generate_answer_general"
]]:
    """Classify user intent and pre-generate search query in parallel.
    
    Runs intent classification and query generation concurrently,
    then routes to 'acknowledge' for research or 'generate_answer_general'
    for general questions.
    """
    writer = get_stream_writer()
    writer({"type": "simple_thinking", "message": "OpenTA is thinking..."})
    writer({"type": "status", "step": "classifying", "message": "Understanding your question..."})

    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    intent_classifier = state.get("intent_classifier")
    query_generator = state.get("query_generator")

    # Run intent classification + query generation in parallel
    intent_task = None
    query_task = None

    if intent_classifier:
        intent_task = asyncio.create_task(
            _run_dspy_sync(intent_classifier, cheap_lm=cheap_lm, question=question)
        )
    if query_generator:
        query_task = asyncio.create_task(
            _run_dspy_sync(query_generator, cheap_lm=cheap_lm, user_question=question)
        )

    # Await intent classification
    is_research = True
    if intent_task:
        try:
            intent_res = await intent_task
            is_research = intent_res.category != "general"
            logger.info("[LG-NODE] Intent: %s", intent_res.category)
        except Exception as e:
            logger.warning("[LG-NODE] Intent classification failed (%s) — defaulting to research", e)

    # Await query generation
    pre_generated_query = None
    if query_task:
        if not is_research:
            query_task.cancel()
        else:
            try:
                query_result = await query_task
                pre_generated_query = query_result.search_query
                logger.info("[LG-NODE] Pre-generated query: '%s'", pre_generated_query)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[LG-NODE] Pre-query generation failed: %s", e)

    writer({
        "type": "status",
        "step": "classified",
        "message": (
            "Research question detected" if is_research
            else "General question — no paper search needed"
        ),
    })

    if is_research:
        return Command(
            update={"is_research": True, "pre_generated_query": pre_generated_query},
            goto="acknowledge"
        )
    else:
        return Command(
            update={"is_research": False},
            goto="generate_answer_general"
        )


# ---------------------------------------------------------------------------
# Node: acknowledge
# ---------------------------------------------------------------------------

async def acknowledge(state: RAGGraphState) -> dict:
    """Generate acknowledgment for research questions, then go to plan."""
    writer = get_stream_writer()
    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    ack_gen = state.get("acknowledgment_generator")

    if ack_gen:
        try:
            ack_result = await _run_dspy_sync(
                ack_gen, cheap_lm=cheap_lm, question=question
            )
            ack_text = getattr(ack_result, "acknowledgment", "")
            if ack_text:
                writer({"type": "acknowledgment", "content": ack_text})
                return {"acknowledgment": ack_text}
        except Exception as e:
            logger.warning("[LG-NODE] Acknowledgment generation failed: %s", e)

    return {}


# ---------------------------------------------------------------------------
# Node: create_plan
# ---------------------------------------------------------------------------

async def create_plan(state: RAGGraphState) -> dict:
    """Generate a research plan using the DSPy ResearchPlanner."""
    writer = get_stream_writer()
    writer({"type": "status", "step": "planning", "message": "Planning approach..."})

    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    planner = state.get("planner")

    use_default = _should_use_default_plan(question)

    if planner and not use_default:
        try:
            steps = await asyncio.to_thread(
                lambda: planner.create_plan(
                    question=question, is_research=True, cheap_lm=cheap_lm
                )
            )
            logger.info("[LG-NODE] Planner created %d steps", len(steps))
        except Exception as e:
            logger.warning("[LG-NODE] Planner failed (%s) — using default plan", e)
            steps = default_plan(True)
    else:
        steps = default_plan(True)
        logger.info("[LG-NODE] Using default plan (heuristic)")

    writer({
        "type": "plan",
        "steps": [s.model_dump() for s in steps],
    })

    return {"plan_steps": steps, "current_step_idx": 0}


# ---------------------------------------------------------------------------
# Node: execute_step (search + thinking for one plan step)
# ---------------------------------------------------------------------------

async def execute_step(state: RAGGraphState) -> dict:
    """Execute a single plan step: optional search + thinking.
    
    After execution, the graph edge goes to route_steps_node
    which decides if more steps remain.
    """
    writer = get_stream_writer()
    plan_steps = state.get("plan_steps", [])
    idx = state.get("current_step_idx", 0)

    if idx >= len(plan_steps):
        return {}

    step = plan_steps[idx]
    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    retriever = state.get("retriever")
    query_generator = state.get("query_generator")
    query_reformulator = state.get("query_reformulator")
    query_decomposer = state.get("query_decomposer")
    planner = state.get("planner")

    existing_papers = state.get("all_papers", [])

    writer({
        "type": "step_start",
        "step_id": step.id,
        "title": step.title,
        "description": step.description,
    })

    new_papers = []
    new_context = []

    # Search action (if needed)
    if step.needs_search and retriever:
        pre_generated_query = state.get("pre_generated_query") if idx == 0 else None

        # Import and re-use the search step helper from streaming.py
        from app.utils.streaming import _execute_search_step

        if pre_generated_query is None:
            writer({
                "type": "step_action",
                "step_id": step.id,
                "action": "generating_query",
            })

        search_query, papers, context, original_query = await _execute_search_step(
            step, question, retriever, query_generator, cheap_lm,
            pre_generated_query=pre_generated_query,
            query_reformulator=query_reformulator,
            query_decomposer=query_decomposer,
            paper_offset=len(existing_papers),
        )

        # Emit reformulation notice if it happened
        if original_query is not None:
            writer({
                "type": "step_action",
                "step_id": step.id,
                "action": "reformulated_query",
                "original_query": original_query,
                "query": search_query,
            })

        new_papers = papers
        new_context = [context] if context else []

        writer({
            "type": "step_action",
            "step_id": step.id,
            "action": "search",
            "query": search_query,
        })
        writer({
            "type": "step_action_result",
            "step_id": step.id,
            "action": "search",
            "paper_count": len(papers),
        })

    # Step thinking (stream via writer)
    if planner:
        gathered = _paper_summary(existing_papers + new_papers)
        try:
            # Use dspy.streamify for streaming thinking tokens
            streaming_thinker = dspy.streamify(
                planner.step_thinker,
                stream_listeners=[
                    dspy.streaming.StreamListener(signature_field_name="thinking")
                ],
            )
            ctx = dspy.context(lm=cheap_lm) if cheap_lm else contextlib.nullcontext()
            with ctx:
                async for value in streaming_thinker(
                    question=question,
                    step_title=step.title,
                    step_description=step.description,
                    gathered_context=gathered,
                ):
                    if (
                        isinstance(value, dspy.streaming.StreamResponse)
                        and value.chunk
                    ):
                        writer({
                            "type": "step_thinking",
                            "step_id": step.id,
                            "content": value.chunk,
                        })
        except Exception as e:
            logger.warning("[LG-NODE] Step thinking failed: %s", e)

    writer({"type": "step_done", "step_id": step.id})

    # Clear pre_generated_query after first step uses it
    update = {
        "current_step_idx": idx + 1,
        "all_papers": new_papers,
        "all_context_parts": new_context,
    }
    if idx == 0:
        update["pre_generated_query"] = None

    return update


# ---------------------------------------------------------------------------
# Node: generate_answer_general (for non-research questions)
# ---------------------------------------------------------------------------

async def generate_answer_general(state: RAGGraphState) -> dict:
    """Generate answer for general (non-research) questions using DSPy PaperRAG."""
    writer = get_stream_writer()
    question = state["question"]
    history = state.get("history")
    rag_module = state.get("rag_module")

    if history is None:
        import dspy as _dspy
        history = _dspy.History(messages=[])

    writer({"type": "thinking_start"})
    writer({"type": "answer_start"})

    streaming_program = dspy.streamify(
        rag_module,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="reasoning"),
            dspy.streaming.StreamListener(signature_field_name="answer"),
        ],
    )

    final_answer = ""
    _emitted_thinking_end = False

    async for value in streaming_program(
        question=question,
        context="No paper context needed for this general query.",
        history=history,
    ):
        if isinstance(value, dspy.streaming.StreamResponse) and value.chunk:
            field = getattr(value, "signature_field_name", "answer")
            if field == "reasoning":
                writer({"type": "thinking_token", "content": value.chunk})
            else:
                if not _emitted_thinking_end:
                    writer({"type": "thinking_end"})
                    _emitted_thinking_end = True
                writer({"type": "token", "content": value.chunk})
        elif isinstance(value, dspy.Prediction):
            if not _emitted_thinking_end:
                writer({"type": "thinking_end"})
            final_answer = getattr(value, "answer", str(value))
            writer({"type": "done", "content": final_answer, "sources": []})

    return {
        "final_answer": final_answer,
        "final_sources": [],
        "cited_papers": [],
        "gap_verdict": "complete",
    }


# ---------------------------------------------------------------------------
# Node: generate_answer (for research questions, after all steps)
# ---------------------------------------------------------------------------

async def generate_answer(state: RAGGraphState) -> dict:
    """Generate the final answer using accumulated context from all steps."""
    writer = get_stream_writer()
    question = state["question"]
    history = state.get("history")
    rag_module = state.get("rag_module")
    all_papers = state.get("all_papers", [])
    all_context_parts = state.get("all_context_parts", [])

    if history is None:
        import dspy as _dspy
        history = _dspy.History(messages=[])

    writer({"type": "answer_start"})
    writer({"type": "thinking_start"})

    # Deduplicate papers
    seen_ids: set = set()
    unique_papers: list = []
    for p in all_papers:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            unique_papers.append(p)

    combined_context = (
        "\n\n".join(all_context_parts)
        if all_context_parts
        else "No paper context available for this general question."
    )

    # Stream CoT reasoning + answer
    streaming_program = dspy.streamify(
        rag_module,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="reasoning"),
            dspy.streaming.StreamListener(signature_field_name="answer"),
        ],
    )

    final_answer = ""
    final_sources = []
    cited_papers_list = []
    _emitted_thinking_end = False

    # Keepalive before potentially long LLM call
    writer({"type": "_keepalive"})

    async for value in streaming_program(
        question=question, context=combined_context, history=history
    ):
        if isinstance(value, dspy.streaming.StreamResponse) and value.chunk:
            field = getattr(value, "signature_field_name", "answer")
            if field == "reasoning":
                writer({"type": "thinking_token", "content": value.chunk})
            else:
                if not _emitted_thinking_end:
                    writer({"type": "thinking_end"})
                    _emitted_thinking_end = True
                writer({"type": "token", "content": value.chunk})
        elif isinstance(value, dspy.Prediction):
            if not _emitted_thinking_end:
                writer({"type": "thinking_end"})
                _emitted_thinking_end = True
            cited_papers_list = _build_cited_papers(
                getattr(value, "sources", []), unique_papers
            )
            final_answer = getattr(value, "answer", str(value))
            final_sources = [p.model_dump() for p in cited_papers_list]
            writer({
                "type": "done",
                "content": final_answer,
                "sources": final_sources,
            })

    # Citation audit
    if cited_papers_list or final_answer:
        audit = _audit_citations(final_answer, cited_papers_list)
        writer({"type": "citation_audit", **audit})
        if not audit["is_clean"]:
            logger.warning(
                "[LG-NODE] Hallucinated citations: %s",
                audit["hallucinated_citation_numbers"],
            )

    return {
        "final_answer": final_answer,
        "final_sources": final_sources,
        "cited_papers": cited_papers_list,
    }


# ---------------------------------------------------------------------------
# Node: detect_gap
# ---------------------------------------------------------------------------

async def detect_gap(state: RAGGraphState) -> Command[Literal[
    "refine_answer", "post_answer"
]]:
    """Check if the generated answer has gaps that need refinement."""
    question = state["question"]
    final_answer = state.get("final_answer", "")
    is_research = state.get("is_research", False)
    gap_detector = state.get("gap_detector")
    cheap_lm = state.get("cheap_lm")

    if not gap_detector or not is_research or not final_answer:
        return Command(update={"gap_verdict": "complete"}, goto="post_answer")

    try:
        gap_result = await _run_dspy_sync(
            gap_detector, cheap_lm=cheap_lm,
            question=question, answer=final_answer,
        )
        verdict = getattr(gap_result, "verdict", "complete")
        gap_query = getattr(gap_result, "gap_query", "").strip()

        if verdict == "partial" and gap_query:
            logger.info("[LG-NODE] Gap detected. Query: '%s'", gap_query)
            writer = get_stream_writer()
            writer({"type": "refinement_start", "gap_query": gap_query})
            return Command(
                update={"gap_verdict": "partial", "gap_query_text": gap_query},
                goto="refine_answer"
            )
    except Exception as e:
        logger.warning("[LG-NODE] Gap detection failed: %s", e)

    return Command(update={"gap_verdict": "complete"}, goto="post_answer")


# ---------------------------------------------------------------------------
# Node: refine_answer
# ---------------------------------------------------------------------------

async def refine_answer(state: RAGGraphState) -> dict:
    """Re-generate answer with enriched context after gap detection."""
    writer = get_stream_writer()
    question = state["question"]
    history = state.get("history")
    rag_module = state.get("rag_module")
    retriever = state.get("retriever")
    all_papers = state.get("all_papers", [])
    all_context_parts = state.get("all_context_parts", [])
    gap_query = state.get("gap_query_text", "")

    if history is None:
        import dspy as _dspy
        history = _dspy.History(messages=[])

    # Retrieve additional context for the gap
    extra_context, extra_papers = await retriever.get_papers_with_context(gap_query)
    writer({"type": "refinement_search", "paper_count": len(extra_papers)})

    # Merge papers
    seen_ids = {p.id for p in all_papers}
    new_papers = [p for p in extra_papers if p.id not in seen_ids]
    for p in new_papers:
        seen_ids.add(p.id)
    all_refinement_papers = all_papers + new_papers

    # Deduplicate
    seen_dedup: set = set()
    unique_papers: list = []
    for p in all_refinement_papers:
        if p.id not in seen_dedup:
            seen_dedup.add(p.id)
            unique_papers.append(p)

    combined_context = "\n\n".join(all_context_parts)
    if extra_context:
        combined_context += "\n\n" + extra_context

    # Stream refined answer
    refinement_program = dspy.streamify(
        rag_module,
        stream_listeners=[
            dspy.streaming.StreamListener(signature_field_name="answer")
        ],
    )

    refined_answer = ""
    refined_sources = []

    writer({"type": "_keepalive"})

    async for rval in refinement_program(
        question=question, context=combined_context, history=history
    ):
        if isinstance(rval, dspy.streaming.StreamResponse) and rval.chunk:
            writer({"type": "refinement_token", "content": rval.chunk})
        elif isinstance(rval, dspy.Prediction):
            refined_cited = _build_cited_papers(
                getattr(rval, "sources", []), unique_papers
            )
            refined_answer = getattr(rval, "answer", "")
            refined_sources = [p.model_dump() for p in refined_cited]
            writer({
                "type": "refinement_done",
                "content": refined_answer,
                "sources": refined_sources,
            })

    return {
        "final_answer": refined_answer or state.get("final_answer", ""),
        "final_sources": refined_sources or state.get("final_sources", []),
    }


# ---------------------------------------------------------------------------
# Node: post_answer (callbacks: on_complete, generate_title)
# ---------------------------------------------------------------------------

async def post_answer(state: RAGGraphState) -> dict:
    """Handle post-answer tasks: save history, generate title."""
    writer = get_stream_writer()
    final_answer = state.get("final_answer", "")
    final_sources = state.get("final_sources", [])
    on_complete = state.get("on_complete")
    generate_title_fn = state.get("generate_title_fn")
    question = state["question"]
    is_first_message = state.get("is_first_message", False)

    # Save history
    if on_complete:
        try:
            await on_complete(
                answer=final_answer,
                sources=final_sources,
                search_query=state.get("pre_generated_query"),
            )
        except Exception as e:
            logger.warning("[LG-NODE] on_complete callback failed: %s", e)

    # Generate title
    title = None
    if generate_title_fn and is_first_message:
        try:
            title = await generate_title_fn(question=question, answer=final_answer)
            writer({"type": "title", "content": title})
        except Exception as e:
            logger.warning("[LG-NODE] Title generation failed: %s", e)

    return {"title": title}


