# GitHub Issues for DSPy → LangChain/LangGraph Migration

## Issue Template Reference

All issues should follow this structure:
- **Title**: [Phase X] Actionable description
- **Description**: Context + acceptance criteria
- **Dependencies**: Links to blocking issues
- **Labels**: `phase-{1-5}`, `enhancement`, `migration`
- **Priority**: P0 (critical) → P3 (nice-to-have)

---

## Issue #1: [Phase 1] Set up LangGraph infrastructure

**Title**: `[Phase 1] Install LangGraph dependencies and create base service layer`

**Description**:
Install LangChain and LangGraph dependencies without modifying existing DSPy code. Create new `GraphAgentService` class alongside existing `RAGService`.

**Acceptance Criteria**:
- [ ] `langgraph`, `langchain-core`, `langchain-openai` added to `requirements.txt`
- [ ] `backend/app/services/graph_agent.py` created with empty class
- [ ] Basic `ResearchState` TypedDict defined
- [ ] Existing `/chat/basic` endpoint still works (no regressions)
- [ ] Unit test: can import `GraphAgentService`

**Dependencies**: None

**Labels**: `phase-1`, `enhancement`, `good-first-issue`

**Estimated Effort**: 2 hours

---

## Issue #2: [Phase 1] Create basic StateGraph with 2 nodes

**Title**: `[Phase 1] Implement basic LangGraph StateGraph (classify → answer)`

**Description**:
Create a minimal working LangGraph with 2 nodes: intent classification and answer generation. Test with general questions only (no retrieval yet).

**Acceptance Criteria**:
- [ ] `ResearchState` schema with all required fields defined
- [ ] `StateGraph` with 2 nodes: `classify_intent` and `generate_answer`
- [ ] Conditional edge routes "general" → `generate_answer`, "research" → END
- [ ] New endpoint `/chat/graph` works for general questions
- [ ] SSE streaming emits same events as `/chat/basic`
- [ ] Integration test: general query returns answer

**Dependencies**: #1

**Labels**: `phase-1`, `enhancement`

**Estimated Effort**: 4 hours

---

## Issue #3: [Phase 2] Migrate Intent Classifier to LangGraph node

**Title**: `[Phase 2] Wrap DSPy IntentClassifier as LangGraph node`

**Description**:
Create LangGraph node that wraps the existing DSPy `IntentClassifier` module. This establishes the pattern for wrapping DSPy modules as nodes.

**Acceptance Criteria**:
- [ ] `intent_classifier_node()` function created
- [ ] Calls DSPy `IntentClassifier` module (unchanged)
- [ ] Returns dict with `{"intent_category": result.category}`
- [ ] Node integrated into StateGraph
- [ ] Unit test: node returns correct classification for sample queries

**Dependencies**: #2

**Labels**: `phase-2`, `enhancement`

**Estimated Effort**: 2 hours

---

## Issue #4: [Phase 2] Migrate Query Generator to LangGraph node

**Title**: `[Phase 2] Wrap DSPy QueryGenerator as LangGraph node`

**Description**:
Create LangGraph node for `QueryGenerator`. Enable parallel execution by running intent classification and query generation in parallel.

**Acceptance Criteria**:
- [ ] `query_generator_node()` function created
- [ ] Calls DSPy `QueryGenerator` module (unchanged)
- [ ] Returns dict with `{"search_query": result.search_query}`
- [ ] StateGraph updated: both `classify_intent` and `generate_query` run from START in parallel
- [ ] Unit test: node generates optimized search query

**Dependencies**: #3

**Labels**: `phase-2`, `enhancement`

**Estimated Effort**: 2 hours

---

## Issue #5: [Phase 2] Migrate Research Planner to LangGraph node

**Title**: `[Phase 2] Wrap DSPy ResearchPlanner as LangGraph node`

**Description**:
Create LangGraph node for `ResearchPlanner`. Add conditional edge to route research questions through planning step.

**Acceptance Criteria**:
- [ ] `research_planner_node()` function created
- [ ] Calls DSPy `ResearchPlanner.create_plan()` (unchanged)
- [ ] Returns dict with `{"plan_steps": [...], "current_step_index": 0}`
- [ ] Conditional edge: "research" → plan_research, "general" → generate_answer
- [ ] Integration test: research query returns plan with 2-3 steps

**Dependencies**: #4

**Labels**: `phase-2`, `enhancement`

**Estimated Effort**: 3 hours

---

## Issue #6: [Phase 2] Migrate Paper Retriever to LangGraph node

**Title**: `[Phase 2] Wrap PaperRetriever as LangGraph node with Send API for parallelism`

**Description**:
Create retrieval node that supports both single-query and multi-query strategies. Use LangGraph's `Send` API for parallel sub-query execution.

**Acceptance Criteria**:
- [ ] `fan_out_retrieval()` function creates `Send` objects for parallel tasks
- [ ] `retrieve_node()` executes retrieval for one query
- [ ] Supports both `single` and `multi_query` strategies
- [ ] State accumulator merges results from parallel tasks
- [ ] Integration test: multi-query strategy returns papers from 2-4 sub-queries

**Dependencies**: #5

**Labels**: `phase-2`, `enhancement`, `performance`

**Estimated Effort**: 6 hours

---

## Issue #7: [Phase 2] Implement step execution loop

**Title**: `[Phase 2] Implement plan step execution loop with step_thinking streaming`

**Description**:
Add loop logic to execute plan steps sequentially. Stream thinking tokens for each step using existing SSE events.

**Acceptance Criteria**:
- [ ] Conditional edge checks `current_step_index < len(plan_steps)`
- [ ] `step_thinker_node()` streams thinking per step
- [ ] Loop continues until all steps complete
- [ ] SSE events: `step_start`, `step_thinking`, `step_done`
- [ ] Integration test: 3-step plan executes all steps

**Dependencies**: #6

**Labels**: `phase-2`, `enhancement`, `streaming`

**Estimated Effort**: 8 hours

---

## Issue #8: [Phase 2] Migrate PaperRAG to LangGraph node

**Title**: `[Phase 2] Wrap DSPy PaperRAG as LangGraph node with ChainOfThought streaming`

**Description**:
Create final answer generation node. Stream reasoning tokens and answer tokens using existing SSE event format.

**Acceptance Criteria**:
- [ ] `generate_answer_node()` calls DSPy `PaperRAG` (unchanged)
- [ ] Uses `dspy.streamify` for CoT reasoning streaming
- [ ] SSE events: `thinking_start`, `thinking_token`, `thinking_end`, `token`
- [ ] Returns dict with `{"answer": ..., "reasoning": ..., "sources": ...}`
- [ ] Integration test: returns cited answer with CoT

**Dependencies**: #7

**Labels**: `phase-2`, `enhancement`, `streaming`

**Estimated Effort**: 6 hours

---

## Issue #9: [Phase 2] Migrate Gap Detector to LangGraph node

**Title**: `[Phase 2] Wrap DSPy GapDetector as LangGraph node with re-retrieval flow`

**Description**:
Add gap detection after answer generation. If gap detected, route to additional retrieval followed by answer regeneration.

**Acceptance Criteria**:
- [ ] `gap_detector_node()` calls DSPy `GapDetector` (unchanged)
- [ ] Returns dict with `{"gap_detected": bool, "gap_query": ...}`
- [ ] Conditional edge: complete → END, partial → retrieve_gap → regenerate_answer
- [ ] Integration test: gap triggers re-retrieval and regeneration

**Dependencies**: #8

**Labels**: `phase-2`, `enhancement`

**Estimated Effort**: 4 hours

---

## Issue #10: [Phase 2] Streaming parity with /chat/basic

**Title**: `[Phase 2] Achieve streaming parity with /chat/basic endpoint`

**Description**:
Ensure `/chat/graph` emits identical SSE events as `/chat/basic` for frontend compatibility. Map all 10+ event types correctly.

**Acceptance Criteria**:
- [ ] All SSE events from `/chat/basic` implemented in `/chat/graph`
- [ ] Event payloads have same structure (verified with tests)
- [ ] Streaming latency within 5% of baseline
- [ ] Frontend works identically with both endpoints
- [ ] Comparison test: same query produces same events (modulo LLM variance)

**Dependencies**: #9

**Labels**: `phase-2`, `enhancement`, `streaming`, `testing`

**Estimated Effort**: 6 hours

---

## Issue #11: [Phase 3] Add checkpointing with persistence

**Title**: `[Phase 3] Implement LangGraph checkpointing with Redis/Postgres backend`

**Description**:
Add state checkpointing to enable pause/resume and long-running query support. Store checkpoints in Redis or Postgres.

**Acceptance Criteria**:
- [ ] `PostgresCheckpointer` or `RedisSaver` configured
- [ ] `thread_id` passed to `graph.invoke()` for state persistence
- [ ] Checkpoints saved after each node execution
- [ ] `graph.invoke(None, config)` resumes from last checkpoint
- [ ] Integration test: pause after step 2, resume continues

**Dependencies**: #10

**Labels**: `phase-3`, `enhancement`, `persistence`

**Estimated Effort**: 8 hours

---

## Issue #12: [Phase 3] Add human-in-the-loop interrupts

**Title**: `[Phase 3] Implement human-in-the-loop with interrupt() for plan approval`

**Description**:
Add optional manual review before executing research plan. Use LangGraph's `interrupt()` to pause execution and surface plan for approval.

**Acceptance Criteria**:
- [ ] `interrupt()` in planning node surfaces plan to frontend
- [ ] Frontend can approve/reject or edit plan
- [ ] `Command(resume=...)` continues execution with approved/edited plan
- [ ] Opt-in via `meta_params.enable_human_review`
- [ ] Integration test: interrupt → approve → execution continues

**Dependencies**: #11

**Labels**: `phase-3`, `enhancement`, `feature`

**Estimated Effort**: 8 hours

---

## Issue #13: [Phase 3] Add RetryPolicy for external API calls

**Title**: `[Phase 3] Add RetryPolicy to retriever nodes for resilience`

**Description**:
Configure `RetryPolicy` on retrieval nodes to handle transient failures from Voyage AI, PGVector, and external APIs.

**Acceptance Criteria**:
- [ ] `RetryPolicy` configured with max_attempts=3, exponential backoff
- [ ] Applied to `retrieve_node` and `retrieve_gap_node`
- [ ] Retries on `RateLimitError`, `TimeoutError`, `ConnectionError`
- [ ] Logs retry attempts with context
- [ ] Integration test: transient error triggers retry, succeeds on 2nd attempt

**Dependencies**: #11

**Labels**: `phase-3`, `enhancement`, `reliability`

**Estimated Effort**: 4 hours

---

## Issue #14: [Phase 3] Implement subgraphs for modularity

**Title**: `[Phase 3] Extract retrieval and generation into subgraphs`

**Description**:
Refactor monolithic graph into subgraphs: `RetrievalSubgraph` and `GenerationSubgraph`. Enables independent testing and reuse.

**Acceptance Criteria**:
- [ ] `RetrievalSubgraph` encapsulates retrieval logic
- [ ] `GenerationSubgraph` encapsulates answer generation
- [ ] Main graph composes subgraphs as nodes
- [ ] Subgraphs have isolated state schemas
- [ ] Unit tests for each subgraph independently

**Dependencies**: #11

**Labels**: `phase-3`, `enhancement`, `refactoring`

**Estimated Effort**: 6 hours

---

## Issue #15: [Phase 4] Integrate DSPy teleprompter for prompt optimization

**Title**: `[Phase 4] Run DSPy BootstrapFewShot optimizer on PaperRAG module`

**Description**:
Use DSPy's teleprompter to optimize prompts for PaperRAG. Compile with few-shot examples and track performance improvements.

**Acceptance Criteria**:
- [ ] `BootstrapFewShot` optimizer configured
- [ ] Training dataset from historical Q&A pairs
- [ ] Compiled PaperRAG module saved
- [ ] Metrics logged (answer quality, citation accuracy)
- [ ] A/B test: optimized vs baseline prompts

**Dependencies**: #14

**Labels**: `phase-4`, `enhancement`, `optimization`

**Estimated Effort**: 8 hours

---

## Issue #16: [Phase 4] Build automated prompt optimization pipeline

**Title**: `[Phase 4] Create weekly automated prompt optimization with MLflow tracking`

**Description**:
Automate DSPy prompt optimization with weekly runs. Track prompt versions and performance in MLflow.

**Acceptance Criteria**:
- [ ] Cron job or GitHub Action runs weekly optimization
- [ ] New prompts evaluated against test dataset
- [ ] Best prompts logged to MLflow with version tags
- [ ] Auto-deploy if metrics improve by >5%
- [ ] Manual approval required for deployment

**Dependencies**: #15

**Labels**: `phase-4`, `enhancement`, `automation`

**Estimated Effort**: 6 hours

---

## Issue #17: [Phase 4] Implement hybrid DSPy+LangChain mode

**Title**: `[Phase 4] Create hybrid mode: DSPy for critical nodes, raw LangChain for simple nodes`

**Description**:
Optimize by using DSPy-optimized prompts for critical nodes (PaperRAG, GapDetector) and raw LangChain for simple nodes (IntentClassifier, QueryGenerator).

**Acceptance Criteria**:
- [ ] Configuration flag: `use_dspy_optimized_prompts`
- [ ] Critical nodes use DSPy-optimized prompts when enabled
- [ ] Simple nodes use direct LangChain LLM calls
- [ ] Performance metrics: latency, cost, quality
- [ ] A/B test: hybrid vs all-DSPy mode

**Dependencies**: #15

**Labels**: `phase-4`, `enhancement`, `performance`

**Estimated Effort**: 6 hours

---

## Issue #18: [Phase 5] Feature parity validation suite

**Title**: `[Phase 5] Create comprehensive test suite for feature parity validation`

**Description**:
Build test suite to validate that `/chat/graph` has feature parity with `/chat/basic`. Cover all scenarios and edge cases.

**Acceptance Criteria**:
- [ ] 50+ test cases covering all flows
- [ ] Tests for: general queries, research queries, multi-step plans, gap detection, streaming
- [ ] Quality metrics: BLEU, cosine similarity, citation accuracy
- [ ] Performance tests: latency, throughput, memory
- [ ] All tests pass before cutover

**Dependencies**: #17

**Labels**: `phase-5`, `testing`, `quality`

**Estimated Effort**: 12 hours

---

## Issue #19: [Phase 5] Load testing and performance benchmarks

**Title**: `[Phase 5] Run load tests comparing /chat/basic vs /chat/graph performance`

**Description**:
Execute load tests with production-like traffic. Compare latency, throughput, error rates, and resource usage.

**Acceptance Criteria**:
- [ ] Load test script (Locust/k6)
- [ ] 1000 concurrent users, 10 minute duration
- [ ] Metrics: p50/p95/p99 latency, RPS, error rate, CPU/memory
- [ ] `/chat/graph` within 10% of `/chat/basic` latency
- [ ] Performance report with recommendations

**Dependencies**: #18

**Labels**: `phase-5`, `testing`, `performance`

**Estimated Effort**: 8 hours

---

## Issue #20: [Phase 5] Gradual traffic cutover (10% → 50% → 100%)

**Title**: `[Phase 5] Implement gradual traffic cutover with monitoring and rollback`

**Description**:
Migrate traffic from `/chat/basic` to `/chat/graph` gradually. Monitor metrics and rollback on issues.

**Acceptance Criteria**:
- [ ] Feature flag for traffic split (10/50/100%)
- [ ] Metrics dashboard: error rate, latency, user feedback
- [ ] Automated rollback on error rate spike (>2x baseline)
- [ ] 7-day soak test at each traffic level
- [ ] Final cutover to 100% `/chat/graph`

**Dependencies**: #19

**Labels**: `phase-5`, `deployment`, `monitoring`

**Estimated Effort**: 6 hours

---

## Issue #21: [Phase 5] Deprecate /chat/basic endpoint

**Title**: `[Phase 5] Deprecate /chat/basic and remove legacy code`

**Description**:
Mark `/chat/basic` as deprecated, add migration notice, and remove old code after 30-day grace period.

**Acceptance Criteria**:
- [ ] `/chat/basic` returns deprecation warning in response headers
- [ ] API docs updated with migration guide
- [ ] Frontend updated to use `/chat/graph`
- [ ] 30-day grace period elapsed
- [ ] Old code removed: `stream_dspy_response()`, legacy flow
- [ ] Unit tests updated

**Dependencies**: #20

**Labels**: `phase-5`, `deprecation`, `cleanup`

**Estimated Effort**: 4 hours

---

## Issue #22: [Phase 5] Update documentation and migration guide

**Title**: `[Phase 5] Update API docs, architecture docs, and create migration guide for users`

**Description**:
Update all documentation to reflect new LangGraph-based architecture. Create migration guide for API consumers.

**Acceptance Criteria**:
- [ ] API documentation updated (OpenAPI spec)
- [ ] Architecture docs updated with LangGraph diagrams
- [ ] Migration guide for API users
- [ ] Changelog with migration notes
- [ ] Code examples updated in README

**Dependencies**: #21

**Labels**: `phase-5`, `documentation`

**Estimated Effort**: 6 hours

---

## Issue #23: [Exploration] Evaluate Deep Agents for simple query fallback

**Title**: `[Exploration] Assess Deep Agents library for handling simple/general queries`

**Description**:
Evaluate whether Deep Agents (langchain-ai/deepagents) can replace the simple query flow. Benchmark performance and quality.

**Acceptance Criteria**:
- [ ] Proof of concept using Deep Agents
- [ ] Performance comparison: latency, cost, quality
- [ ] Recommendation: use or don't use
- [ ] If using: integration plan
- [ ] If not using: document rationale

**Dependencies**: None (can run in parallel)

**Labels**: `exploration`, `research`, `optional`

**Estimated Effort**: 8 hours

---

## Issue #24: [Exploration] Implement LangSmith tracing

**Title**: `[Exploration] Add LangSmith tracing for observability and debugging`

**Description**:
Enable LangSmith tracing for LangGraph execution. Replace manual MLflow logging with LangSmith's automatic tracing.

**Acceptance Criteria**:
- [ ] LangSmith API key configured
- [ ] Traces visible in LangSmith dashboard
- [ ] Trace data: inputs, outputs, latency, tokens
- [ ] Comparison with existing MLflow logging
- [ ] Decision: migrate fully or hybrid approach

**Dependencies**: None (can run in parallel)

**Labels**: `exploration`, `observability`, `optional`

**Estimated Effort**: 4 hours

---

## Issue #25: [Enhancement] Multi-agent supervisor pattern

**Title**: `[Enhancement] Implement supervisor pattern for multi-agent collaboration`

**Description**:
Add a supervisor agent that delegates to specialized worker agents (e.g., retrieval specialist, analysis specialist, synthesis specialist).

**Acceptance Criteria**:
- [ ] Supervisor node created with routing logic
- [ ] 2-3 worker agent nodes
- [ ] Supervisor routes based on query type
- [ ] Integration test: complex query routed correctly
- [ ] Performance vs single-agent comparison

**Dependencies**: #14

**Labels**: `enhancement`, `feature`, `multi-agent`

**Estimated Effort**: 12 hours

---

## Summary

| Phase | Issues | Total Effort | Duration |
|-------|--------|--------------|----------|
| Phase 1 | #1-#2 | 6 hours | 1-2 weeks |
| Phase 2 | #3-#10 | 41 hours | 3-4 weeks |
| Phase 3 | #11-#14 | 26 hours | 2-3 weeks |
| Phase 4 | #15-#17 | 20 hours | 2 weeks |
| Phase 5 | #18-#22 | 36 hours | 2-3 weeks |
| Exploration | #23-#25 | 24 hours | Parallel |
| **TOTAL** | **25 issues** | **153 hours** | **10-12 weeks** |

---

## Quick Start: First 5 Issues

If you want to start immediately, these are the first 5 issues to tackle:

1. **#1**: Install dependencies (2h) - Low risk, pure setup
2. **#2**: Create basic StateGraph (4h) - Establishes foundation
3. **#3**: Migrate IntentClassifier (2h) - Simple node pattern
4. **#4**: Migrate QueryGenerator (2h) - Adds parallelism
5. **#5**: Migrate ResearchPlanner (3h) - Adds planning flow

**Total for first 5 issues**: 13 hours (~2 days for a focused developer)
