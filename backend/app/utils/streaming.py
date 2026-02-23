"""
Streaming utilities for Server-Sent Events (SSE).

Implements a Manus-like planning + execution UX:
  plan → step loop (think + optional search) → stream final answer
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, AsyncGenerator, List

import dspy

from app.core.models import CitedPaper
from app.services.planner import PlanStep, ResearchPlanner, default_plan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _build_cited_papers(
    source_ids: List[str], retrieved_papers: list
) -> List[CitedPaper]:
    paper_map = {p.id: p for p in retrieved_papers}
    cited: List[CitedPaper] = []
    seen: set = set()
    for i, pid in enumerate(source_ids, 1):
        if pid in seen:
            continue
        seen.add(pid)
        paper = paper_map.get(pid)
        if paper:
            cited.append(
                CitedPaper(
                    id=paper.id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                    year=paper.year,
                    citation_number=i,
                )
            )
    return cited


def _paper_summary(papers: list) -> str:
    if not papers:
        return "No papers retrieved yet."
    lines = ["Retrieved papers:"]
    for i, p in enumerate(papers, 1):
        lines.append(f"  {i}. {p.title} ({p.year})")
    return "\n".join(lines)


def _audit_citations(answer: str, cited_papers: list) -> dict:
    """
    Pure-Python citation hallucination check.
    Scans answer text for [N] references and flags any N that exceeds
    the number of actually retrieved papers.
    No LLM call — zero latency overhead.
    """
    import re
    cited_nums = {int(n) for n in re.findall(r'\[(\d+)\]', answer)}
    valid_nums = {p.citation_number for p in cited_papers}
    hallucinated = sorted(cited_nums - valid_nums)
    return {
        "is_clean": len(hallucinated) == 0,
        "hallucinated_citation_numbers": hallucinated,
        "total_citations_in_answer": len(cited_nums),
        "total_papers_available": len(cited_papers),
    }


# ---------------------------------------------------------------------------
# DSPy async helpers
# ---------------------------------------------------------------------------

async def _run_dspy_sync(fn, cheap_lm=None, **kwargs):
    """Run a blocking DSPy call in a thread pool so it doesn't stall the event loop."""
    def _call():
        ctx = dspy.context(lm=cheap_lm) if cheap_lm else contextlib.nullcontext()
        with ctx:
            return fn(**kwargs)
    return await asyncio.to_thread(_call)


def _should_use_default_plan(question: str) -> bool:
    """
    Heuristic: use default_plan (skip the planner LLM call) for simple questions.
    A question is considered simple if it has fewer than 20 words and no
    multi-faceted keywords that suggest a comparative or multi-step analysis.
    """
    words = question.split()
    if len(words) >= 20:
        return False
    complex_keywords = {"compare", "comparison", "difference", "differences", "versus",
                        "vs", "also", "additionally", "furthermore", "contrast"}
    return not any(w.lower().strip("?,.:") in complex_keywords for w in words)


# ---------------------------------------------------------------------------
# Step execution helpers
# ---------------------------------------------------------------------------

async def _execute_search_step(
    step: PlanStep,
    question: str,
    retriever: Any,
    query_generator: Any,
    cheap_lm: Any,
    pre_generated_query: str | None = None,
    query_reformulator: Any = None,
) -> tuple[str, list, str, str | None]:
    """
    Runs query generation + retrieval for a search step.
    Returns (search_query, papers, context_string, original_query_if_reformulated).
    - If pre_generated_query is provided it is used directly.
    - If retrieval returns 0 papers and query_reformulator is provided,
      reformulates the query and retries once.
    - original_query_if_reformulated is non-None only when reformulation occurred.
    """
    if pre_generated_query:
        search_query = pre_generated_query
    elif query_generator:
        query_result = await _run_dspy_sync(
            query_generator, cheap_lm=cheap_lm, user_question=question
        )
        search_query = query_result.search_query
    else:
        search_query = question

    context, papers = await retriever.get_papers_with_context(search_query)

    # Zero-result retry: reformulate and try once more
    if len(papers) == 0 and query_reformulator:
        original_query = search_query
        reformulation = await _run_dspy_sync(
            query_reformulator, cheap_lm=cheap_lm, original_query=search_query
        )
        broader_query = reformulation.broader_query.strip()
        if broader_query and broader_query != search_query:
            context, papers = await retriever.get_papers_with_context(broader_query)
            return broader_query, papers, context, original_query

    return search_query, papers, context, None


async def _stream_step_thinking(
    planner: ResearchPlanner,
    step: PlanStep,
    question: str,
    gathered_context: str,
    cheap_lm: Any,
) -> AsyncGenerator[str, None]:
    """Streams the thinking for a single step via SSE step_thinking events."""
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
            gathered_context=gathered_context,
        ):
            if (
                isinstance(value, dspy.streaming.StreamResponse)
                and value.chunk
            ):
                yield format_sse(
                    {
                        "type": "step_thinking",
                        "step_id": step.id,
                        "content": value.chunk,
                    }
                )


# ---------------------------------------------------------------------------
# Main streaming entry point
# ---------------------------------------------------------------------------

async def stream_dspy_response(
    dspy_program: Any,
    retriever: Any,
    question: str,
    query_generator: Any = None,
    intent_classifier: Any = None,
    acknowledgment_generator: Any = None,
    cheap_lm: Any = None,
    history: Any = None,
    language: str = "en-US",
    source_preference: str = "all",
    include_metadata: bool = False,
    planner: ResearchPlanner | None = None,
    on_complete: Any = None,
    generate_title: Any = None,
    query_reformulator: Any = None,
    gap_detector: Any = None,
) -> AsyncGenerator[str, None]:
    """
    on_complete:     async callable(answer, sources, search_query) — save history.
    generate_title:  async callable(question, answer) -> str — generate conversation
                     title; when provided a 'title' SSE event is emitted after 'done'.
    """
    """
    Stream a planning-first agent response as SSE events.

    SSE event contract (in emission order):
      status        { step, message }
      plan          { steps: [{id, title, description, needs_search}] }
      step_start    { step_id, title, description }
      step_action   { step_id, action: "search", query }
      step_action_result { step_id, action: "search", paper_count }
      step_thinking { step_id, content }   ← streamed tokens
      step_done     { step_id }
      answer_start  {}
      token         { content }            ← streamed tokens
      done          { content, sources[] }
      error         { content }
    """
    start_time = time.time()
    token_count = 0

    if history is None:
        history = dspy.History(messages=[])

    logger.info("[STREAM] Starting for question: '%s'", question)

    try:
        # ------------------------------------------------------------------ #
        # 1. Show thinking state (shimmer in UI)                             #
        # ------------------------------------------------------------------ #
        yield format_sse(
            {"type": "simple_thinking", "message": "OpenTA is thinking..."}
        )

        # ------------------------------------------------------------------ #
        # 2. Classify intent + pre-generate query in parallel                 #
        # ------------------------------------------------------------------
        yield format_sse(
            {"type": "status", "step": "classifying", "message": "Understanding your question..."}
        )

        t_intent_start = time.perf_counter()

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

        is_research = True
        pre_generated_query: str | None = None

        if intent_task:
            intent_res = await intent_task
            is_research = intent_res.category != "general"
            logger.info(
                "[STREAM] Intent: %s (%.2fs)",
                intent_res.category, time.perf_counter() - t_intent_start
            )

        yield format_sse(
            {
                "type": "status",
                "step": "classified",
                "message": (
                    "Research question detected"
                    if is_research
                    else "General question — no paper search needed"
                ),
            }
        )

        # ------------------------------------------------------------------ #
        # 2b. Generate acknowledgment for research questions                 #
        # ------------------------------------------------------------------ #
        if is_research and acknowledgment_generator:
            try:
                acknowledgment_result = await _run_dspy_sync(
                    acknowledgment_generator,
                    cheap_lm=cheap_lm,
                    question=question
                )
                if acknowledgment_result:
                    acknowledgment = getattr(acknowledgment_result, 'acknowledgment', '')
                    if acknowledgment:
                        logger.info("[STREAM] Generated acknowledgment for research question")
                        yield format_sse({
                            "type": "acknowledgment",
                            "content": acknowledgment
                        })
            except Exception as e:
                logger.warning("[STREAM] Failed to generate acknowledgment: %s", e)
                # Continue without acknowledgment - not critical

        # ------------------------------------------------------------------ #
        # 2. General questions: skip planning entirely, go straight to answer #
        # ------------------------------------------------------------------ #
        if not is_research:
            if query_task:
                query_task.cancel()
            yield format_sse({"type": "answer_start"})

            streaming_program = dspy.streamify(
                dspy_program,
                stream_listeners=[
                    dspy.streaming.StreamListener(signature_field_name="answer")
                ],
            )
            async for value in streaming_program(
                question=question,
                context="No paper context needed for this general query.",
                history=history,
            ):
                if isinstance(value, dspy.streaming.StreamResponse) and value.chunk:
                    token_count += 1
                    yield format_sse({"type": "token", "content": value.chunk})
                elif isinstance(value, dspy.Prediction):
                    general_answer = getattr(value, "answer", str(value))
                    yield format_sse({"type": "done", "content": general_answer, "sources": []})
                    if on_complete:
                        await on_complete(answer=general_answer, sources=[], search_query=None)
                    if generate_title:
                        try:
                            title = await generate_title(question=question, answer=general_answer)
                            yield format_sse({"type": "title", "content": title})
                        except Exception as _te:
                            logger.warning("[STREAM] Title generation error: %s", _te)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info("[STREAM] General answer completed (%d tokens, %dms)", token_count, duration_ms)
            yield "data: [DONE]\n\n"
            return

        # ------------------------------------------------------------------ #
        # 3. Research questions: create plan                                   #
        # ------------------------------------------------------------------ #
        # Collect pre-generated query (parallel task started earlier)
        if query_task:
            try:
                query_result = await query_task
                pre_generated_query = query_result.search_query
                logger.info("[STREAM] Pre-generated query: '%s'", pre_generated_query)
            except asyncio.CancelledError:
                pre_generated_query = None

        yield format_sse(
            {"type": "status", "step": "planning", "message": "Planning approach..."}
        )

        t_plan_start = time.perf_counter()
        use_default = _should_use_default_plan(question)
        if planner and not use_default:
            steps = await asyncio.to_thread(
                lambda: planner.create_plan(question=question, is_research=is_research, cheap_lm=cheap_lm)
            )
            logger.info("[STREAM] Planner LLM call took %.2fs", time.perf_counter() - t_plan_start)
        else:
            steps = default_plan(is_research)
            logger.info("[STREAM] Using default_plan (heuristic skipped planner LLM call)")

        yield format_sse(
            {
                "type": "plan",
                "steps": [s.model_dump() for s in steps],
            }
        )

        # ------------------------------------------------------------------ #
        # 4. Execute steps                                                     #
        # ------------------------------------------------------------------ #
        all_papers: list = []
        all_context_parts: list[str] = []
        gathered_context = "No information gathered yet."

        for step in steps:
            t_step_start = time.perf_counter()
            logger.info(
                "[STREAM] Step %d/%d: '%s'", step.id + 1, len(steps), step.title
            )

            yield format_sse(
                {
                    "type": "step_start",
                    "step_id": step.id,
                    "title": step.title,
                    "description": step.description,
                }
            )

            # Search action (if needed)
            if step.needs_search:
                # Only show "generating_query" if we don't already have one
                if pre_generated_query is None:
                    yield format_sse(
                        {
                            "type": "step_action",
                            "step_id": step.id,
                            "action": "generating_query",
                        }
                    )

                search_query, papers, context, original_query = await _execute_search_step(
                    step, question, retriever, query_generator, cheap_lm,
                    pre_generated_query=pre_generated_query,
                    query_reformulator=query_reformulator,
                )
                # Only use pre_generated_query for the first search step
                pre_generated_query = None

                # Emit reformulation notice if it happened
                if original_query is not None:
                    yield format_sse(
                        {
                            "type": "step_action",
                            "step_id": step.id,
                            "action": "reformulated_query",
                            "original_query": original_query,
                            "query": search_query,
                        }
                    )

                all_papers.extend(papers)
                all_context_parts.append(context)

                logger.info(
                    "[STREAM] Step %d search: query='%s', found %d papers (%.2fs total)",
                    step.id, search_query, len(papers), time.perf_counter() - t_step_start
                )

                yield format_sse(
                    {
                        "type": "step_action",
                        "step_id": step.id,
                        "action": "search",
                        "query": search_query,
                    }
                )
                yield format_sse(
                    {
                        "type": "step_action_result",
                        "step_id": step.id,
                        "action": "search",
                        "paper_count": len(papers),
                    }
                )

                # Update gathered context for subsequent steps
                gathered_context = _paper_summary(all_papers)

            # Stream step thinking
            if planner:
                async for sse_chunk in _stream_step_thinking(
                    planner, step, question, gathered_context, cheap_lm
                ):
                    yield sse_chunk

            yield format_sse({"type": "step_done", "step_id": step.id})

        # ------------------------------------------------------------------ #
        # 5. Stream final answer                                               #
        # ------------------------------------------------------------------ #
        yield format_sse({"type": "answer_start"})

        # Deduplicate papers across search steps
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

        streaming_program = dspy.streamify(
            dspy_program,
            stream_listeners=[
                dspy.streaming.StreamListener(signature_field_name="answer")
            ],
        )

        t_answer_start = time.perf_counter()
        logger.info("[STREAM] Generating final answer...")

        async for value in streaming_program(
            question=question, context=combined_context, history=history
        ):
            if isinstance(value, dspy.streaming.StreamResponse) and value.chunk:
                token_count += 1
                yield format_sse({"type": "token", "content": value.chunk})

            elif isinstance(value, dspy.Prediction):
                cited_papers = _build_cited_papers(
                    getattr(value, "sources", []), unique_papers
                )
                final_answer = getattr(value, "answer", str(value))
                final_sources = [p.model_dump() for p in cited_papers]
                yield format_sse(
                    {
                        "type": "done",
                        "content": final_answer,
                        "sources": final_sources,
                    }
                )
                if on_complete:
                    await on_complete(
                        answer=final_answer,
                        sources=final_sources,
                        search_query=pre_generated_query,
                    )

                # Citation hallucination audit (pure Python, no LLM call)
                audit = _audit_citations(final_answer, cited_papers)
                yield format_sse({"type": "citation_audit", **audit})
                if not audit["is_clean"]:
                    logger.warning(
                        "[STREAM] Hallucinated citations detected: %s",
                        audit["hallucinated_citation_numbers"],
                    )

                # Adaptive gap-filling re-retrieval (only for research questions)
                if gap_detector and is_research:
                    try:
                        gap_result = await _run_dspy_sync(
                            gap_detector, cheap_lm=cheap_lm,
                            question=question, answer=final_answer,
                        )
                        if (
                            getattr(gap_result, "verdict", "complete") == "partial"
                            and getattr(gap_result, "gap_query", "").strip()
                        ):
                            gap_q = gap_result.gap_query.strip()
                            logger.info("[STREAM] Gap detected. Refining with query: '%s'", gap_q)
                            yield format_sse({"type": "refinement_start", "gap_query": gap_q})

                            extra_context, extra_papers = await retriever.get_papers_with_context(gap_q)
                            yield format_sse({"type": "refinement_search", "paper_count": len(extra_papers)})

                            # Merge unique new papers into existing set
                            new_papers = [p for p in extra_papers if p.id not in seen_ids]
                            for p in new_papers:
                                seen_ids.add(p.id)
                            all_refinement_papers = unique_papers + new_papers
                            enriched_context = combined_context + ("\n\n" + extra_context if extra_context else "")

                            # Re-generate with enriched context, streaming refinement tokens
                            refinement_program = dspy.streamify(
                                dspy_program,
                                stream_listeners=[
                                    dspy.streaming.StreamListener(signature_field_name="answer")
                                ],
                            )
                            async for rval in refinement_program(
                                question=question, context=enriched_context, history=history
                            ):
                                if isinstance(rval, dspy.streaming.StreamResponse) and rval.chunk:
                                    yield format_sse({"type": "refinement_token", "content": rval.chunk})
                                elif isinstance(rval, dspy.Prediction):
                                    refined_cited = _build_cited_papers(
                                        getattr(rval, "sources", []), all_refinement_papers
                                    )
                                    yield format_sse({
                                        "type": "refinement_done",
                                        "content": getattr(rval, "answer", ""),
                                        "sources": [p.model_dump() for p in refined_cited],
                                    })
                    except Exception as _ge:
                        logger.warning("[STREAM] Gap detection/refinement failed: %s", _ge)

                # Generate and emit title (only when caller requests it)
                if generate_title:
                    try:
                        title = await generate_title(question=question, answer=final_answer)
                        yield format_sse({"type": "title", "content": title})
                    except Exception as _te:
                        logger.warning("[STREAM] Title generation error: %s", _te)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "[STREAM] Final answer took %.2fs; Completed (%d tokens, %dms total)",
            time.perf_counter() - t_answer_start, token_count, duration_ms
        )

        if include_metadata:
            yield format_sse(
                {"type": "metadata", "token_count": token_count, "duration_ms": duration_ms}
            )

        yield "data: [DONE]\n\n"

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "[STREAM] Error after %dms: %s", duration_ms, e, exc_info=True
        )
        yield format_sse({"type": "error", "content": str(e)})
        yield "data: [DONE]\n\n"


def create_stream_chunk(
    chunk_type: str,
    content: str | None = None,
    sources: list[str] | None = None,
) -> str:
    data: dict = {"type": chunk_type}
    if content is not None:
        data["content"] = content
    if sources is not None:
        data["sources"] = sources
    return format_sse(data)
