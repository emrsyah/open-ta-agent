# DSPy Basics - A Complete Beginner's Guide

## Table of Contents
1. [What is DSPy?](#what-is-dspy)
2. [Installation](#installation)
3. [Core Concepts](#core-concepts)
4. [Your First DSPy Program](#your-first-dspy-program)
5. [Understanding Signatures](#understanding-signatures)
6. [Working with Modules](#working-with-modules)
7. [Configuring Language Models](#configuring-language-models)
8. [Building Custom Modules](#building-custom-modules)
9. [Optimizing Your Programs](#optimizing-your-programs)
10. [Evaluation](#evaluation)

---

## What is DSPy?

**DSPy** is a framework for **programming** language models instead of **prompting** them.

### The Problem DSPy Solves

Traditional approach (painful):
```python
# Old way - constantly tweaking prompt strings
prompt = "You are a helpful assistant. Please answer this question: {question}"
response = llm(prompt.format(question="What is DSPy?"))

# Want to change the behavior? Rewrite the entire prompt!
prompt = "You are an EXPERT assistant. Think step by step. Question: {question}"
```

DSPy approach (declarative):
```python
# DSPy way - define what you want, not how to prompt
class QuestionAnswering(dspy.Signature):
    """Answer questions with facts."""
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()

qa = dspy.ChainOfThought(QuestionAnswering)
result = qa(question="What is DSPy?")
```

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Declarative** | Define input/output, not prompts |
| **Modular** | Compose reusable components |
| **Portable** | Swap LMs without code changes |
| **Optimizable** | Auto-improve prompts & weights |
| **Systematic** | Built-in evaluation framework |

---

## Installation

```bash
pip install dspy-ai
```

For specific features:
```bash
# For retrieval (RAG applications)
pip install dspy-ai[retrieval]

# For all extras
pip install dspy-ai[all]
```

---

## Core Concepts

DSPy has three main building blocks:

```
┌─────────────────────────────────────────────────────────────┐
│                        DSPy Program                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │  Signature  │ -> │   Module    │ -> │     LM      │    │
│  │  (What)     │    │   (How)     │    │  (Engine)   │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 1. **Signatures** - WHAT you want
Declarative input/output specifications

### 2. **Modules** - HOW to do it
Pre-built strategies for invoking LMs

### 3. **Language Models (LMs)** - The engine
Configured backends (OpenAI, local, etc.)

---

## Your First DSPy Program

### Step 1: Configure a Language Model

```python
import dspy

# Option A: Using OpenAI
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-api-key')
dspy.configure(lm=lm)

# Option B: Using environment variable (recommended)
import os
lm = dspy.LM('openai/gpt-4o-mini', api_key=os.getenv('OPENAI_API_KEY'))
dspy.configure(lm=lm)
```

### Step 2: Define a Signature

```python
class BasicQA(dspy.Signature):
    """Answer questions with short, factual answers."""
    
    question = dspy.InputField(desc="The question to answer")
    answer = dspy.OutputField(desc="A short, factual answer")
```

**What's happening:**
- `dspy.Signature` - Base class for all signatures
- `"""..."""` - Docstring tells the LM what this signature does
- `dspy.InputField()` - Defines an input
- `dspy.OutputField()` - Defines an output
- `desc=` - Optional description to guide the LM

### Step 3: Use a Module

```python
# Create a predictor
predict = dspy.Predict(BasicQA)

# Run it
result = predict(question="What is the capital of France?")

# Access the output
print(result.answer)  # Output: Paris
```

---

## Understanding Signatures

Signatures are the most important concept in DSPy. They define the **contract** between your input and output.

### Basic Signature

```python
class SentimentAnalysis(dspy.Signature):
    """Analyze the sentiment of a text."""
    
    text: str = dspy.InputField()
    sentiment: str = dspy.OutputField()
```

### Signature with Types

```python
from typing import Literal

class SentimentAnalysis(dspy.Signature):
    """Analyze the sentiment of a text."""
    
    text: str = dspy.InputField()
    sentiment: Literal["positive", "negative", "neutral"] = dspy.OutputField()
```

### Signature with Descriptions

```python
class QuestionAnswering(dspy.Signature):
    """Answer questions based on given context."""
    
    context: str = dspy.InputField(desc="Background information to use")
    question: str = dspy.InputField(desc="The question to answer")
    answer: str = dspy.OutputField(desc="Answer based only on the context")
```

### Signature with Complex Types

```python
from typing import List

class DocumentSummary(dspy.Signature):
    """Summarize a document into key points."""
    
    document: str = dspy.InputField(desc="The document to summarize")
    key_points: List[str] = dspy.OutputField(desc="3-5 bullet point summary")
    title: str = dspy.OutputField(desc="A descriptive title")
```

### Compact Syntax (Shorthand)

```python
# Instead of defining a class, you can use a string
qa = dspy.Predict("question -> answer")

# With multiple inputs
rag = dspy.Predict("question, context -> answer")

# This is equivalent to:
class QA(dspy.Signature):
    question = dspy.InputField()
    answer = dspy.OutputField()
```

---

## Working with Modules

Modules are pre-built strategies that work with any signature.

### 1. dspy.Predict - The Basic Module

```python
# Simple prediction
predict = dspy.Predict("question -> answer")
result = predict(question="What is 2+2?")
print(result.answer)  # Output: 4
```

### 2. dspy.ChainOfThought - Reasoning Module

Makes the LM think step-by-step before answering:

```python
# With ChainOfThought
cot = dspy.ChainOfThought("question -> answer")
result = cot(question="If 3 cats eat 3 fish in 3 minutes, 
                    how long for 100 cats to eat 100 fish?")

# Access the reasoning
print(result.rationale)  # Shows the step-by-step thinking
print(result.answer)     # Output: 3 minutes
```

**When to use ChainOfThought:**
- Math problems
- Logic puzzles
- Complex reasoning
- When you want to see the LM's thought process

### 3. dspy.ReAct - Tool-Using Agent

Allows the LM to use tools:

```python
# Define a signature
class ToolUseQA(dspy.Signature):
    """Answer questions using available tools."""
    question = dspy.InputField()
    answer = dspy.OutputField()

# Create a ReAct agent with tools
agent = dspy.ReAct(ToolUseQA, tools=["search", "calculator"])

# Run
result = agent(question="What is 123 * 456 + 789?")
print(result.answer)
```

### Module Comparison

| Module | Best For | Adds |
|--------|----------|-----|
| `dspy.Predict` | Simple tasks | Nothing |
| `dspy.ChainOfThought` | Reasoning | Thinking steps |
| `dspy.ProgramOfThought` | Code problems | Code execution |
| `dspy.ReAct` | Multi-step tasks | Tool use |
| `dspy.MultiChainComparison` | Critical tasks | Multiple tries |

---

## Configuring Language Models

DSPy supports many LMs through a unified interface.

### OpenAI Models

```python
import dspy

# GPT-4o-mini (recommended for cost-effectiveness)
gpt4o_mini = dspy.LM('openai/gpt-4o-mini', api_key='your-key')

# GPT-4o (for complex tasks)
gpt4o = dspy.LM('openai/gpt-4o', api_key='your-key')

# Set as default
dspy.configure(lm=gpt4o_mini)
```

### Local Models (via OpenAI-compatible APIs)

```python
# Using a local server (e.g., Ollama, LM Studio, vLLM)
local_lm = dspy.LM(
    'openai/local-model',
    api_base='http://localhost:11434/v1',
    api_key='dummy-key'
)
dspy.configure(lm=local_lm)
```

### Using Environment Variables (Recommended)

```python
import os
import dspy

# Set env var: OPENAI_API_KEY=sk-...
lm = dspy.LM('openai/gpt-4o-mini', api_key=os.getenv('OPENAI_API_KEY'))
dspy.configure(lm=lm)
```

### Multiple LMs in One Program

```python
# Configure multiple LMs
fast_lm = dspy.LM('openai/gpt-4o-mini')
smart_lm = dspy.LM('openai/gpt-4o')

# Use the fast one by default
dspy.configure(lm=fast_lm)

# Override for specific module
cot = dspy.ChainOfThought("question -> answer")
cot.set_lm(smart_lm)  # This module uses smart_lm
```

---

## Building Custom Modules

Custom modules let you compose multiple steps into reusable components.

### Basic Custom Module

```python
import dspy

class MyCustomModule(dspy.Module):
    def __init__(self):
        super().__init__()
        # Initialize sub-modules
        self.step1 = dspy.Predict("input -> intermediate")
        self.step2 = dspy.Predict("intermediate -> output")
    
    def forward(self, input_value):
        # Step 1
        result1 = self.step1(input=input_value)
        
        # Step 2
        result2 = self.step2(intermediate=result1.intermediate)
        
        # Return final result
        return dspy.Prediction(output=result2.output)

# Use it
module = MyCustomModule()
result = module(input_value="Hello")
print(result.output)
```

### Practical Example: RAG Pipeline

```python
class RAG(dspy.Module):
    """Retrieval-Augmented Generation pipeline."""
    
    def __init__(self):
        super().__init__()
        # Query generator
        self.query_gen = dspy.Predict("question -> query")
        # Answer generator
        self.answer_gen = dspy.ChainOfThought("question, context -> answer")
    
    def forward(self, question):
        # Step 1: Generate search query
        query_result = self.query_gen(question=question)
        
        # Step 2: Retrieve context (mock function)
        context = retrieve_from_database(query_result.query)
        
        # Step 3: Generate answer
        answer_result = self.answer_gen(
            question=question, 
            context=context
        )
        
        return dspy.Prediction(
            query=query_result.query,
            context=context,
            answer=answer_result.answer
        )

# Helper function (you'd replace this with real retrieval)
def retrieve_from_database(query):
    return f"Mock context for query: {query}"

# Use the RAG module
rag = RAG()
result = rag(question="What is DSPy?")
print(result.answer)
```

---

## Optimizing Your Programs

DSPy can automatically optimize your prompts and LM weights.

### Why Optimize?

Without optimization:
```python
# Works, but performance varies
qa = dspy.ChainOfThought("question -> answer")
```

With optimization:
```python
# Automatically learns best prompts/demonstrations
from dspy.teleprompt import BootstrapFewShot

# Define a metric (how to measure success)
def exact_match(gold, pred, trace=None):
    return gold.answer.lower() == pred.answer.lower()

# Create training data
trainset = [
    dspy.Example(question="2+2=?", answer="4"),
    dspy.Example(question="3+3=?", answer="6"),
    # ... more examples
]

# Optimize
optimizer = BootstrapFewShot(metric=exact_match, max_bootstrapped_demos=3)
optimized_qa = optimizer.compile(student=qa, trainset=trainset)

# Now use the optimized version
result = optimized_qa(question="5+5=?")
```

### What Optimization Does

1. **Generates demonstrations** from your training data
2. **Finds the best prompts** for your specific task
3. **Can fine-tune weights** (with BootstrapFinetune)
4. **Improves reliability** and performance

---

## Evaluation

Measure how well your DSPy programs work.

### Basic Evaluation

```python
from dspy.evaluate import Evaluate

# Define test set
devset = [
    dspy.Example(question="Capital of France?", answer="Paris"),
    dspy.Example(question="Capital of Japan?", answer="Tokyo"),
    # ... more examples
]

# Define metric
def exact_match(gold, pred, trace=None):
    return gold.answer.lower() == pred.answer.lower()

# Set up evaluator
evaluator = Evaluate(
    devset=devset,
    metric=exact_match,
    num_threads=1,
    display_progress=True,
    display_table=3
)

# Evaluate
evaluator(qa)
# Output: 85% accuracy (17/20)
```

### Comparing Modules

```python
# Compare Predict vs ChainOfThought
predict = dspy.Predict("question -> answer")
cot = dspy.ChainOfThought("question -> answer")

print("Evaluating Predict:")
evaluator(predict)

print("\nEvaluating ChainOfThought:")
evaluator(cot)
```

---

## Quick Reference Cheat Sheet

### Essential Imports
```python
import dspy
from dspy.teleprompt import BootstrapFewShot
from dspy.evaluate import Evaluate
```

### Basic Workflow
```python
# 1. Configure LM
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-key')
dspy.configure(lm=lm)

# 2. Define signature
class MySignature(dspy.Signature):
    """Description of what this does."""
    input_field: str = dspy.InputField()
    output_field: str = dspy.OutputField()

# 3. Create module
module = dspy.ChainOfThought(MySignature)

# 4. Run
result = module(input_field="your input")
print(result.output_field)
```

### Module Selection Guide
- **Simple I/O** → `dspy.Predict`
- **Need reasoning** → `dspy.ChainOfThought`
- **Need tools** → `dspy.ReAct`
- **Custom pipeline** → `class dspy.Module`

### Common Patterns
```python
# Compact signature
"input -> output"

# Multiple inputs
"input1, input2 -> output"

# With types
class Sig(dspy.Signature):
    text: str = dspy.InputField()
    sentiment: Literal["pos", "neg", "neu"] = dspy.OutputField()
```

---

## Next Steps

1. **Practice**: Build simple signatures and modules
2. **Experiment**: Try different modules on the same task
3. **Learn RAG**: Build retrieval-augmented applications
4. **Optimize**: Use teleprompters to improve performance
5. **Explore**: Check out DSPy's advanced features

---

## Additional Resources

- **Official Docs**: https://dspy.ai
- **Tutorials**: https://dspy.ai/tutorials
- **GitHub**: https://github.com/stanfordnlp/dspy
- **Context7 Library**: `/websites/dspy_ai` (use Context7 MCP)

---

Happy DSPy programming! 🚀
