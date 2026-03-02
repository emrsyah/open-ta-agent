# GitHub Issues for DSPy → LangChain/LangGraph Migration

## Compact Issue Set (10 issues covering full migration)

---

## Issue #1: [Phase 1] LangGraph foundation and basic StateGraph

**Title**: `MIG-1: Set up LangGraph infrastructure with basic classify → answer flow`

**Description**:
Install LangChain/LangGraph dependencies and create a minimal working StateGraph with intent classification and answer generation. Establish the foundation for the full migration.

**Scope**:
- Install `langgraph`, `langchain-core`, `langchain-openai`
- Create `backend/app/services/graph_agent.py`
- Define `ResearchState` TypedDict schema
- Implement 2-node graph: `classify_intent` → `generate_answer`
- Create new endpoint `/chat/graph` (keep `/chat/basic` working)
- Add basic SSE streaming (same event format as current)

**Acceptance Criteria**:
- [ ] Dependencies installed, no regressions in `/chat/basic`
- [ ] `ResearchState` schema with all required fields defined
- [ ] `GraphAgentService` class with basic `StateGraph` compiled
- [ ] `intent_classifier_node()` wraps DSPy `IntentClassifier`
- [ ] `generate_answer_node()` wraps DSPy `PaperRAG`
- [ ] `/chat/graph` works for general questions (no retrieval yet)
- [ ] SSE events: `simple_thinking`, `token`, `done`
- [ ] Integration test passes

**Dependencies**: None

**Labels**: `migration`, `phase-1`, `foundation`

**Estimated Effort**: 6 hours

---

## Issue #2: [Phase 2] Query generation and research planning

**Title**: `MIG-2: Add query generation, research planner, and routing logic`

**Description**:
Extend the graph to handle research queries with search query generation and research planning. Add conditional routing based on intent classification.

**Scope**:
- `query_generator_node()` wraps DSPy `QueryGenerator`
- `research_planner_node()` wraps DSPy `ResearchPlanner`
- Conditional edge: research → plan_research, general → generate_answer
- Parallel execution: classify + query_gen run concurrently from START
- `acknowledgment_node()` for pre-research acknowledgment

**Acceptance Criteria**:
- [ ] Query generation node produces optimized search keywords
- [ ] Research planner returns 2-3 step plan with SmartPlanStep objects
- [ ] Conditional routing works: research queries go through planning
- [ ] Acknowledgment generated for research questions only
- [ ] State includes: `intent_category`, `search_query`, `plan_steps`
- [ ] Integration test: research query triggers planning flow

**Dependencies**: #1

**Labels**: `migration`, `phase-2`, `orchestration`

**Estimated Effort**: 8 hours

---

## Issue #3: [Phase 2] Paper retrieval with parallel multi-query support

**Title**: `MIG-3: Implement retrieval node with Send API for parallel sub-query execution`

**Description**:
Build the retrieval layer supporting both single-query and multi-query strategies. Use LangGraph's `Send` API for parallel execution of sub-queries.

**Scope**:
- `fan_out_retrieval()` creates `Send` objects for parallel tasks
- `retrieve_node()` executes PaperRetriever for one query
- `QueryDecomposer` integration for multi-query strategy
- State accumulator merges results from parallel retrievals
- Query reformulation fallback on zero results

**Acceptance Criteria**:
- [ ] Single-query path: 1 search → return papers
- [ ] Multi-query path: decompose → parallel retrieval → merge results
- [ ] Zero-result retry with `QueryReformulator`
- [ ] State includes: `retrieved_papers`, `context`
- [ ] Integration test: multi-query returns papers from 2-4 sub-queries

**Dependencies**: #2

**Labels**: `migration`, `phase-2`, `retrieval`, `performance`

**Estimated Effort**: 10 hours

---

## Issue #4: [Phase 2] Multi-step plan execution with step thinking streaming

**Title**: `MIG-4: Implement plan step execution loop with per-step thinking streaming`

**Description**:
Add the step execution loop that iterates through research plan steps. Stream thinking tokens for each step using existing SSE event format.

**Scope**:
- Loop logic: execute steps sequentially, track `current_step_index`
- `step_thinker_node()` streams thinking per step using DSPy `StepThinkingSignature`
- Query decomposition based on step's `query_strategy` (single/multi)
- SSE events: `step_start`, `step_action`, `step_action_result`, `step_thinking`, `step_done`
- Accumulate context across all steps

**Acceptance Criteria**:
- [ ] Loop executes all plan steps in order
- [ ] Step thinking streamed for each step
- [ ] Single vs multi-query strategy respected per step
- [ ] Context accumulated: all retrieved papers merged
- [ ] SSE events match current `/chat/basic` format
- [ ] Integration test: 3-step plan completes with streaming

**Dependencies**: #3

**Labels**: `migration`, `phase-2`, `streaming`, `orchestration`

**Estimated Effort**: 12 hours

---

## Issue #5: [Phase 2] Final answer generation with gap detection

**Title**: `MIG-5: Complete RAG flow with CoT streaming and gap detection refinement`

**Description**:
Implement the final answer generation with Chain-of-Thought streaming and gap detection that triggers re-retrieval and refinement when needed.

**Scope**:
- `generate_answer_node()` uses DSPy `PaperRAG` with `dspy.streamify`
- CoT reasoning streaming: `thinking_start`, `thinking_token`, `thinking_end`
- Answer streaming: `token` events
- `gap_detector_node()` wraps DSPy `GapDetector`
- Re-retrieval flow: gap_query → extra_papers → regenerate_answer
- Citation building and audit

**Acceptance Criteria**:
- [ ] Final answer generated with accumulated context from all steps
- [ ] CoT reasoning streamed before answer
- [ ] Gap detection triggers re-retrieval when partial
- [ ] Re-generation uses enriched context (original + gap papers)
- [ ] Citation numbers correctly mapped
- [ ] Citation audit flags hallucinated citations
- [ ] Integration test: gap detected → refinement → complete answer

**Dependencies**: #4

**Labels**: `migration`, `phase-2`, `streaming`, `quality`

**Estimated Effort**: 10 hours

---

## Issue #6: [Phase 2] Streaming parity and production readiness

**Title**: `MIG-6: Achieve feature and streaming parity with /chat/basic endpoint`

**Description**:
Ensure `/chat/graph` emits identical SSE events as `/chat/basic` for full frontend compatibility. Add all remaining features for production readiness.

**Scope**:
- Emit all 10+ SSE event types from current system
- Event payload structure identical (verified with tests)
- Session management integration (Redis + DB)
- Title generation for first message
- Error handling and graceful degradation
- Performance: latency within 10% of baseline

**Acceptance Criteria**:
- [ ] All SSE events from `/chat/basic` available in `/chat/graph`
- [ ] Session history loaded from Redis/DB via `conversation_id`
- [ ] Title generated and saved for first message
- [ ] Errors handled gracefully, proper HTTP status codes
- [ ] p95 latency within 10% of `/chat/basic`
- [ ] Frontend works identically with both endpoints
- [ ] Comparison test: same query produces equivalent responses

**Dependencies**: #5

**Labels**: `migration`, `phase-2`, `streaming`, `production`, `testing`

**Estimated Effort**: 12 hours

---

## Issue #7: [Phase 3] Advanced LangGraph features (checkpointing, retries, subgraphs)

**Title**: `MIG-7: Add checkpointing, RetryPolicy, and subgraphs for production resilience`

**Description**:
Implement advanced LangGraph features for production resilience: state checkpointing for pause/resume, retry policies for external APIs, and subgraphs for modularity.

**Scope**:
- Checkpointing: PostgresCheckpointer or RedisSaver
- Resume execution with `thread_id`
- `RetryPolicy` on retrieval nodes (max_attempts=3, exponential backoff)
- Human-in-the-loop: `interrupt()` for plan approval (opt-in)
- Subgraphs: `RetrievalSubgraph`, `GenerationSubgraph`
- LangSmith tracing integration

**Acceptance Criteria**:
- [ ] Checkpoints saved after each node, persist to Redis/Postgres
- [ ] `graph.invoke(None, config)` resumes from last checkpoint
- [ ] Retries on transient API failures (RateLimitError, TimeoutError)
- [ ] Optional human review: pause after planning, approve/edit before execution
- [ ] Retrieval and generation encapsulated as subgraphs
- [ ] LangSmith traces visible in dashboard
- [ ] Integration test: pause after step 2, resume continues

**Dependencies**: #6

**Labels**: `migration`, `phase-3`, `reliability`, `observability`

**Estimated Effort**: 16 hours

---

## Issue #8: [Phase 4] DSPy prompt optimization integration

**Title**: `MIG-8: Integrate DSPy teleprompter for automated prompt optimization`

**Description**:
Leverage DSPy's prompt optimization capabilities within the LangGraph framework. Run BootstrapFewShot optimizer and create hybrid mode using optimized prompts for critical nodes.

**Scope**:
- DSPy `BootstrapFewShot` optimizer configuration
- Training dataset from historical Q&A pairs
- Optimize `PaperRAG` and `GapDetector` prompts
- Compiled modules saved with version tracking
- Hybrid mode: DSPy for critical nodes, raw LangChain for simple nodes
- MLflow tracking for prompt versions and metrics
- Automated weekly optimization pipeline

**Acceptance Criteria**:
- [ ] `PaperRAG` module compiled with few-shot examples
- [ ] Optimized prompts improve answer quality by >5%
- [ ] Hybrid mode: DSPy-optimized for PaperRAG/GapDetector, direct LLM for others
- [ ] Prompt versions tracked in MLflow with metrics
- [ ] Weekly automated optimization via GitHub Action
- [ ] A/B test: optimized vs baseline prompts

**Dependencies**: #7

**Labels**: `migration`, `phase-4`, `optimization`, `automation`

**Estimated Effort**: 12 hours

---

## Issue #9: [Phase 5] Testing, benchmarking, and validation

**Title**: `MIG-9: Comprehensive test suite, load testing, and feature parity validation`

**Description**:
Build comprehensive test suite to validate feature parity, run load tests for performance comparison, and ensure quality metrics meet or exceed baseline.

**Scope**:
- 50+ test cases covering all flows and edge cases
- Quality metrics: BLEU, cosine similarity, citation accuracy
- Load testing: 1000 concurrent users, 10-minute duration
- Performance comparison: latency, throughput, resource usage
- A/B testing framework for comparing `/chat/basic` vs `/chat/graph`

**Acceptance Criteria**:
- [ ] All test cases pass (general, research, multi-step, gap detection)
- [ ] Answer quality (BLEU) ≥ baseline, citation accuracy ≥ baseline
- [ ] Load test: p95 latency within 10% of baseline
- [ ] Error rate <0.1%, no memory leaks
- [ ] Performance report with recommendations
- [ ] A/B test results showing parity or improvement

**Dependencies**: #8

**Labels**: `migration`, `phase-5`, `testing`, `performance`, `quality`

**Estimated Effort**: 16 hours

---

## Issue #10: [Phase 5] Traffic cutover, deprecation, and documentation

**Title**: `MIG-10: Gradual traffic cutover, deprecate legacy endpoint, update documentation`

**Description**:
Execute gradual traffic migration from `/chat/basic` to `/chat/graph`, deprecate legacy endpoint, and update all documentation.

**Scope**:
- Gradual cutover: 10% → 50% → 100% over 2-3 weeks
- Monitoring dashboard: error rate, latency, user feedback
- Automated rollback on error spike (>2x baseline)
- Deprecation notice for `/chat/basic` (30-day grace period)
- Update API docs, architecture docs, README
- Create migration guide for API users
- Remove legacy code after grace period

**Acceptance Criteria**:
- [ ] Feature flag for traffic split (10/50/100%)
- [ ] Monitoring dashboard deployed and configured
- [ ] Automated rollback triggered on error spike
- [ ] 7-day soak test at each traffic level
- [ ] `/chat/basic` deprecated with warning headers
- [ ] All documentation updated
- [ ] Legacy code removed after 30 days
- [ ] Frontend using `/chat/graph` exclusively

**Dependencies**: #9

**Labels**: `migration`, `phase-5`, `deployment`, `documentation`

**Estimated Effort**: 12 hours

---

## Optional: Exploration Issues

### Issue #11: [Exploration] Deep Agents evaluation
Evaluate whether Deep Agents library can handle simple queries. PoC with performance comparison.

**Effort**: 8 hours | **Labels**: `exploration`, `optional`

### Issue #12: [Exploration] Multi-agent supervisor pattern
Implement supervisor pattern with specialized worker agents (retrieval specialist, analysis specialist).

**Effort**: 12 hours | **Labels**: `enhancement`, `multi-agent`, `optional`

---

## Summary

| Issue | Focus | Effort | Duration |
|-------|-------|--------|----------|
| #1 | Foundation | 6h | 1 week |
| #2 | Query + Planning | 8h | 1 week |
| #3 | Retrieval | 10h | 1-2 weeks |
| #4 | Step Execution | 12h | 2 weeks |
| #5 | Answer + Gap | 10h | 1-2 weeks |
| #6 | Parity | 12h | 2 weeks |
| #7 | Advanced | 16h | 2-3 weeks |
| #8 | DSPy Optimize | 12h | 2 weeks |
| #9 | Testing | 16h | 2 weeks |
| #10 | Cutover | 12h | 2 weeks |
| **Total (core)** | **10 issues** | **114 hours** | **10-12 weeks** |
| Optional | Explorations | 20h | Parallel |

---

## Dependency Graph

```
#1 (Foundation)
  ↓
#2 (Query + Planning)
  ↓
#3 (Retrieval)
  ↓
#4 (Step Execution)
  ↓
#5 (Answer + Gap)
  ↓
#6 (Parity)
  ↓
#7 (Advanced)
  ↓
#8 (DSPy Optimize)
  ↓
#9 (Testing)
  ↓
#10 (Cutover)
```

**Critical Path**: #1 → #2 → #3 → #4 → #5 → #6 → #7 → #8 → #9 → #10

**Parallel Work**: #11-#12 (exploration) can run anytime alongside main path.

---

## Quick Start

Start with **Issue #1** to set up the foundation. This is low-risk and establishes the infrastructure for all subsequent work.

**First week goal**: Complete #1 and start #2.

**First month goal**: Complete #1-#4 (foundation through step execution).

**First milestone**: End of #6 - full feature parity achieved.


---

## 🗑️ Deletion Checklist (Complete AFTER 30-day grace period)

**⚠️ ONLY DELETE AFTER:**
- [ ] 100% traffic on `/chat/graph` for 14+ days
- [ ] No critical bugs in production
- [ ] Frontend fully migrated
- [ ] API consumers notified
- [ ] 30-day deprecation notice completed

### Files to DELETE:
```bash
# Custom orchestrator (replaced by LangGraph)
backend/app/utils/streaming.py  # After: copy SSE formats to graph_agent.py
```

### Files to UPDATE (remove old route):
```bash
backend/app/api/routes/chat.py  # Remove /chat/basic handler only
```

### Files to KEEP (still in use!):
```bash
# DSPy modules - imported by graph_agent.py as nodes
backend/app/services/rag.py               # DSPy signatures + PaperRAG
backend/app/services/planner.py           # ResearchPlanner
backend/app/services/query_decomposer.py  # QueryDecomposer

# Shared infrastructure
backend/app/services/retriever.py         # PaperRetriever (used by both)
backend/app/utils/parallel_retrieve.py    # Parallel retrieval
backend/app/services/session_manager.py   # Session management
```

### Migration Strategy:
**Don't delete anything during Phases 1-4.** Keep both systems running:
- `/chat/basic` → Old system (production)
- `/chat/graph` → New system (development/testing)

**Phase 5**: Gradual cutover (10% → 50% → 100%), then 30-day grace period, then cleanup.
