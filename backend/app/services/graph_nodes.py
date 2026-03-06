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
from langfuse import observe
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

async def _run_dspy_sync(fn, cheap_lm=None, span_name=None, **kwargs):
    """Run a blocking DSPy call in a thread pool with optional Langfuse span."""
    def _call():
        ctx = dspy.context(lm=cheap_lm) if cheap_lm else contextlib.nullcontext()
        with ctx:
            return fn(**kwargs)

    if span_name:
        _call = observe(name=span_name)(_call)
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

@observe(name="Classify Intent & Generate Query")
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
            _run_dspy_sync(intent_classifier, cheap_lm=cheap_lm, span_name="Intent Classification", question=question)
        )
    if query_generator:
        query_task = asyncio.create_task(
            _run_dspy_sync(query_generator, cheap_lm=cheap_lm, span_name="Search Query Pre-Generation", user_question=question)
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

@observe(name="Generate Acknowledgment")
async def acknowledge(state: RAGGraphState) -> dict:
    """Generate acknowledgment for research questions, then go to plan."""
    writer = get_stream_writer()
    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    ack_gen = state.get("acknowledgment_generator")

    if ack_gen:
        try:
            ack_result = await _run_dspy_sync(
                ack_gen, cheap_lm=cheap_lm, span_name="Acknowledgment Generation", question=question
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

@observe(name="Create Research Plan")
async def create_plan(state: RAGGraphState) -> dict:
    """Generate a context-aware research plan using the DSPy ResearchPlanner.
    
    Passes session context (existing papers, last answer) to enable
    smart planning for follow-up questions like "compare [1] and [2]".
    """
    writer = get_stream_writer()
    writer({"type": "status", "step": "planning", "message": "Planning approach..."})

    question = state["question"]
    cheap_lm = state.get("cheap_lm")
    planner = state.get("planner")
    
    # Get session context for context-aware planning
    session_papers = state.get("session_papers", [])
    last_answer = state.get("last_answer", "")

    use_default = _should_use_default_plan(question)

    needs_retrieval = True
    
    if planner and not use_default:
        try:
            @observe(name="Plan Step Generation")
            def _create_plan():
                return planner.create_plan(
                    question=question,
                    is_research=True,
                    session_papers=session_papers,
                    last_answer=last_answer,
                    cheap_lm=cheap_lm
                )
            needs_retrieval, steps = await asyncio.to_thread(_create_plan)
            logger.info(
                "[LG-NODE] Planner created %d steps, needs_retrieval=%s",
                len(steps), needs_retrieval
            )
        except Exception as e:
            logger.warning("[LG-NODE] Planner failed (%s) — using default plan", e)
            needs_retrieval, steps = True, default_plan(True)
    else:
        needs_retrieval, steps = True, default_plan(True)
        logger.info("[LG-NODE] Using default plan (heuristic)")

    writer({
        "type": "plan",
        "steps": [s.model_dump() for s in steps],
        "needs_retrieval": needs_retrieval,
    })

    return {
        "plan_steps": steps,
        "current_step_idx": 0,
        "needs_retrieval": needs_retrieval,
    }

# ---------------------------------------------------------------------------
# Node: execute_step (search + thinking for one plan step)
# ---------------------------------------------------------------------------

@observe(name="Execute Research Step")
async def execute_step(state: RAGGraphState) -> dict:
    """Execute a single plan step based on its action_type.
    
    Action types:
    - search/research: Retrieve new papers from database
    - compare/summarize/analyze/extract: Use existing papers (no retrieval)
    - clarify: Use previous answer context
    - deep_dive: Fetch full PDF (future)
    - synthesis: Combine findings without new search
    
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
    rag_module = state.get("rag_module")
    history = state.get("history")

    existing_papers = state.get("all_papers", [])
    session_papers = state.get("session_papers", [])
    last_answer = state.get("last_answer", "")

    writer({
        "type": "step_start",
        "step_id": step.id,
        "title": step.title,
        "description": step.description,
        "action_type": step.action_type,
    })

    new_papers = []
    new_context = []

    # ── Handle different action types ──────────────────────────────────────
    
    if step.action_type in ("search", "research"):
        # ── SEARCH: Retrieve new papers from database ──────────────────────
        if retriever:
            pre_generated_query = state.get("pre_generated_query") if idx == 0 else None

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
                catalog_type=state.get("catalog_type"),
                year_from=state.get("year_from"),
                year_to=state.get("year_to"),
                author=state.get("author"),
                has_electronic_access=state.get("has_electronic_access"),
)

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
    
    elif step.action_type in ("compare", "summarize", "analyze", "extract"):
        # ── CONTEXTUAL: Use existing papers without retrieval ───────────────
        writer({
            "type": "step_action",
            "step_id": step.id,
            "action": step.action_type,
            "using_existing_papers": True,
        })
        
        # Resolve which papers to use
        if step.use_cited_papers:
            # Use specific papers by citation number
            papers_to_use = [
                p for p in session_papers
                if p.get("citation_number") in step.use_cited_papers
            ]
            writer({
                "type": "step_action",
                "step_id": step.id,
                "action": "resolved_citations",
                "cited_papers": step.use_cited_papers,
                "resolved_count": len(papers_to_use),
            })
        else:
            # Use all session papers
            papers_to_use = session_papers
        
        # Build context from papers (no retrieval needed)
        if papers_to_use:
            context = _build_context_from_papers(papers_to_use, step.action_type)
            new_context = [context]
            # Don't add to new_papers since these are already in session
            writer({
                "type": "step_action_result",
                "step_id": step.id,
                "action": step.action_type,
                "papers_used": len(papers_to_use),
            })
        else:
            writer({
                "type": "warning",
                "step_id": step.id,
                "message": f"No papers found for {step.action_type} action",
            })
    
    elif step.action_type == "clarify":
        # ── CLARIFY: Re-explain previous answer ─────────────────────────────
        writer({
            "type": "step_action",
            "step_id": step.id,
            "action": "clarify",
            "has_previous_answer": bool(last_answer),
        })
        
        if last_answer:
            # Use last answer as context
            new_context = [f"Previous answer to clarify:\n{last_answer}"]
        else:
            writer({
                "type": "warning",
                "message": "No previous answer to clarify",
            })
    
    elif step.action_type == "synthesis":
        # ── SYNTHESIS: Combine existing findings ────────────────────────────
        writer({
            "type": "step_action",
            "step_id": step.id,
            "action": "synthesis",
            "existing_papers": len(existing_papers),
        })
        # No new retrieval, just mark that we're synthesizing
    
    elif step.action_type == "deep_dive":
        # ── DEEP DIVE: Future - fetch full PDF ─────────────────────────────
        writer({
            "type": "step_action",
            "step_id": step.id,
            "action": "deep_dive",
            "status": "not_yet_implemented",
        })
        logger.warning("[LG-NODE] deep_dive action not yet implemented")

    # ── Step thinking (stream via writer) ───────────────────────────────────
    if planner and step.action_type not in ("clarify",):
        gathered = _paper_summary(existing_papers + new_papers)
        try:
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

    update = {
        "current_step_idx": idx + 1,
        "all_papers": new_papers,
        "all_context_parts": new_context,
    }
    if idx == 0:
        update["pre_generated_query"] = None

    return update


def _build_context_from_papers(papers: list, action_type: str) -> str:
    """Build context string from papers for contextual actions."""
    if not papers:
        return "No papers available for this action."
    
    lines = []
    
    if action_type == "compare":
        lines.append("Papers to compare:")
        for p in papers:
            cn = p.get("citation_number", "?")
            lines.append(f"\n[{cn}] {p.get('title', 'Unknown')}")
            lines.append(f"    Authors: {', '.join(p.get('authors', ['Unknown']))}")
            lines.append(f"    Year: {p.get('year', 'Unknown')}")
            if p.get('abstract'):
                lines.append(f"    Abstract: {p['abstract'][:500]}...")
    
    elif action_type == "summarize":
        lines.append("Papers to summarize:")
        for p in papers:
            cn = p.get("citation_number", "?")
            lines.append(f"\n[{cn}] {p.get('title', 'Unknown')}")
            lines.append(f"    Abstract: {p.get('abstract', 'No abstract available')}")
    
    elif action_type == "analyze":
        lines.append("Papers for analysis:")
        for p in papers:
            cn = p.get("citation_number", "?")
            lines.append(f"\n[{cn}] {p.get('title', 'Unknown')}")
            lines.append(f"    Year: {p.get('year', 'Unknown')}")
            lines.append(f"    Abstract: {p.get('abstract', '')}")
            if p.get('keywords'):
                lines.append(f"    Keywords: {', '.join(p['keywords'])}")
    
    elif action_type == "extract":
        lines.append("Papers for extraction:")
        for p in papers:
            cn = p.get("citation_number", "?")
            lines.append(f"\n[{cn}] {p.get('title', 'Unknown')}")
            lines.append(f"    Authors: {', '.join(p.get('authors', ['Unknown']))}")
            lines.append(f"    Abstract: {p.get('abstract', '')}")
    
    else:
        # Generic fallback
        for p in papers:
            cn = p.get("citation_number", "?")
            lines.append(f"[{cn}] {p.get('title', 'Unknown')} ({p.get('year', 'Unknown')})")
    
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Node: generate_answer_general (for non-research questions)
# ---------------------------------------------------------------------------

@observe(name="Generate Answer (General)")
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

@observe(name="Generate Final Answer")
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

@observe(name="Detect Knowledge Gap")
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
            gap_detector, cheap_lm=cheap_lm, span_name="Gap Analysis",
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

@observe(name="Refine Answer")
async def refine_answer(state: RAGGraphState) -> dict:
    """Re-generate answer with enriched context after gap detection."""
    writer = get_stream_writer()
    question = state["question"]
    history = state.get("history")
    rag_module = state.get("rag_module")
    retriever = state.get("retriever")
    all_papers = state.get("all_papers", [])
    all_context_parts = state.get("all_context_parts", [])
    gap_query = state.get("gap_query_text", "").strip()

    if history is None:
        import dspy as _dspy
        history = _dspy.History(messages=[])

    # Retrieve additional context for the gap (fall back to original question if empty)
    search_query = gap_query or question
    extra_context, extra_papers = await retriever.get_papers_with_context(
        search_query,
        catalog_type=state.get("catalog_type"),
        year_from=state.get("year_from"),
        year_to=state.get("year_to"),
        author=state.get("author"),
        has_electronic_access=state.get("has_electronic_access"),
)
    writer({"type": "refinement_search", "paper_count": len(extra_papers)})
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

@observe(name="Post-Answer Processing")
async def post_answer(state: RAGGraphState) -> dict:
    """Handle post-answer tasks: save history, generate title, update session context."""
    writer = get_stream_writer()
    final_answer = state.get("final_answer", "")
    final_sources = state.get("final_sources", [])
    on_complete = state.get("on_complete")
    generate_title_fn = state.get("generate_title_fn")
    question = state["question"]
    is_first_message = state.get("is_first_message", False)
    conversation_id = state.get("conversation_id")
    is_incognito = state.get("is_incognito", False)
    
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
    
    # Update session context (papers + last answer) for context-aware planning
    if conversation_id and not is_incognito:
        try:
            from app.services.session_manager import get_session_manager
            session_manager = get_session_manager()
            
            # Save last answer and sources
            await session_manager.set_last_answer(
                conversation_id=conversation_id,
                answer=final_answer,
                sources=final_sources,
            )
            
            logger.info(
                "[LG-NODE] Updated session context for %s: %d sources",
                conversation_id,
                len(final_sources),
            )
        except Exception as e:
            logger.warning("[LG-NODE] Failed to update session context: %s", e)

    # Generate title
    title = None
    if generate_title_fn and is_first_message:
        try:
            title = await generate_title_fn(question=question, answer=final_answer)
            writer({"type": "title", "content": title})
        except Exception as e:
            logger.warning("[LG-NODE] Title generation failed: %s", e)

    return {"title": title}

