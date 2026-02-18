# DSPy Research Notes

## Indexed Sources

| Source | Type | ID | Status |
|--------|------|-----|--------|
| DSPy Documentation | Documentation | `27a1a73f-d5bb-475d-a0e6-3154e8a56386` | ✅ Indexed (19 pages) |
| DSPy Context7 | Context7 Library | `/websites/dspy_ai` | ✅ Available (1663 snippets) |
| Stanford DSPy GitHub | Repository | `/stanfordnlp/dspy` | ✅ Available (v3.1.3) |

## Quick Reference

### Nia Search Commands

```python
# Search DSPy documentation
nia_search(query="YOUR QUERY", data_sources=["27a1a73f-d5bb-475d-a0e6-3154e8a56386"])

# Explore DSPy docs structure
nia_nia_explore(source_type="documentation", doc_source_id="27a1a73f-d5bb-475d-a0e6-3154e8a56386", action="tree")

# Read specific page
nia_nia_read(source_type="documentation", doc_source_id="27a1a73f-d5bb-475d-a0e6-3154e8a56386", path="/tutorials/rag")

# Grep in DSPy docs
nia_nia_grep(source_type="documentation", doc_source_id="27a1a73f-d5bb-475d-a0e6-3154e8a56386", pattern="YOUR_PATTERN")
```

### Context7 Commands

```python
# Query DSPy docs
context7_query-docs(
    libraryId="/websites/dspy_ai",
    query="YOUR QUESTION ABOUT DSPY"
)
```

## Key Concepts

### Signatures
Declarative input/output specifications:
```python
class MySignature(dspy.Signature):
    """Description of what this does."""
    input_field: str = dspy.InputField()
    output_field: str = dspy.OutputField()
```

### Modules
- `dspy.Predict` - Basic prediction
- `dspy.ChainOfThought` - Reasoning steps
- `dspy.ReAct` - Tool-using agent
- `dspy.ProgramOfThought` - Code-based reasoning
- Custom modules via `dspy.Module` subclass

### Optimizers (Teleprompters)
- `BootstrapFewShot` - Few-shot learning
- `BootstrapFewShotWithRandomSearch` - Random search optimization
- `MIPROv2` - Multi-stage optimization
- `BootstrapFinetune` - Weight fine-tuning

## Common Patterns

### 1. Basic Classification
```python
classify = dspy.ChainOfThought("text -> sentiment")
result = classify(text="I love this!")
```

### 2. RAG Pipeline
```python
class RAG(dspy.Module):
    def __init__(self):
        self.query_gen = dspy.Predict("question -> query")
        self.generate = dspy.ChainOfThought("question, context -> answer")
    
    def forward(self, question):
        query = self.query_gen(question=question).query
        context = retrieve(query)
        return self.generate(question=question, context=context)
```

### 3. ReAct Agent
```python
agent = dspy.ReAct(tool_names=["search", "calculator"])
result = agent(question="What is 123 * 456?")
```

## Research Date: 2026-02-18
