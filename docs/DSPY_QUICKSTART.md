# DSPy Basics - Quick Start Guide

## 🎯 What You'll Learn

- ✅ How to configure DSPy with a language model
- ✅ How to define signatures (declarative I/O)
- ✅ How to use built-in modules
- ✅ How to build custom modules
- ✅ How to optimize and evaluate programs

---

## 📦 Installation

```bash
pip install dspy-ai
```

---

## 🚀 5-Minute Quick Start

### Step 1: Configure DSPy

```python
import dspy
import os

# Set your API key
lm = dspy.LM('openai/gpt-4o-mini', api_key=os.getenv('OPENAI_API_KEY'))
dspy.configure(lm=lm)
```

### Step 2: Define a Signature

```python
class BasicQA(dspy.Signature):
    """Answer questions with short, factual answers."""
    question = dspy.InputField()
    answer = dspy.OutputField()
```

### Step 3: Use It!

```python
qa = dspy.Predict(BasicQA)
result = qa(question="What is the capital of France?")
print(result.answer)  # Output: Paris
```

---

## 🏗️ Core Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                        DSPy Program                         │
│                                                             │
│  1. SIGNATURE (What)     →  Define inputs/outputs           │
│  2. MODULE (How)         →  Choose a strategy               │
│  3. LANGUAGE MODEL       →  The engine (GPT-4, local, etc)  │
└─────────────────────────────────────────────────────────────┘
```

### 1. Signatures - WHAT You Want

```python
# Simple
class Sentiment(dspy.Signature):
    text: str = dspy.InputField()
    sentiment: str = dspy.OutputField()

# With types
from typing import Literal

class Sentiment(dspy.Signature):
    text: str = dspy.InputField()
    sentiment: Literal["positive", "negative", "neutral"] = dspy.OutputField()

# Compact syntax
"question -> answer"
"question, context -> answer"
```

### 2. Modules - HOW To Do It

| Module | Use For | Example |
|--------|---------|---------|
| `dspy.Predict` | Simple tasks | Text → Summary |
| `dspy.ChainOfThought` | Reasoning | Math problems |
| `dspy.ReAct` | Tool use | Web search |
| `dspy.ProgramOfThought` | Code logic | Algorithmic tasks |

```python
# Basic prediction
predict = dspy.Predict("text -> summary")

# With reasoning
cot = dspy.ChainOfThought("question -> answer")
result = cot(question="Solve: 2x + 5 = 15")
print(result.rationale)  # Shows step-by-step thinking
```

### 3. Language Models - The Engine

```python
# OpenAI
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-key')

# Local (Ollama, vLLM, etc.)
lm = dspy.LM('openai/model', api_base='http://localhost:11434/v1')

# Configure globally
dspy.configure(lm=lm)
```

---

## 📚 Common Patterns

### Pattern 1: Question Answering

```python
class QA(dspy.Signature):
    """Answer questions based on context."""
    context = dspy.InputField(desc="Reference material")
    question = dspy.InputField(desc="Question to answer")
    answer = dspy.OutputField(desc="Answer from context")

qa = dspy.ChainOfThought(QA)
result = qa(
    context="Paris is the capital of France.",
    question="What is the capital of France?"
)
```

### Pattern 2: Classification

```python
from typing import Literal

class Classify(dspy.Signature):
    """Classify text into categories."""
    text = dspy.InputField()
    category = Literal["tech", "sports", "politics"] = dspy.OutputField()

classifier = dspy.Predict(Classify)
result = classifier(text="The new AI model scored 95% accuracy")
```

### Pattern 3: Text Transformation

```python
# Summarization
summarize = dspy.Predict("long_text -> summary")

# Translation
translate = dspy.Predict("text, target_language -> translation")

# Rewrite
rewrite = dspy.Predict("text, style -> rewritten_text")
```

### Pattern 4: Multiple Steps (Custom Module)

```python
class RAG(dspy.Module):
    """Retrieval-Augmented Generation"""
    
    def __init__(self):
        super().__init__()
        self.query_gen = dspy.Predict("question -> query")
        self.answer_gen = dspy.ChainOfThought("question, context -> answer")
    
    def forward(self, question):
        # Step 1: Generate query
        query_result = self.query_gen(question=question)
        
        # Step 2: Retrieve (mock)
        context = retrieve(query_result.query)
        
        # Step 3: Generate answer
        answer_result = self.answer_gen(
            question=question,
            context=context
        )
        
        return dspy.Prediction(answer=answer_result.answer)
```

---

## 🔧 Module Comparison

When to use which module:

```
┌─────────────────────────────────────────────────────────────┐
│                    Decision Tree                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Is your task simple? (direct input→output)                │
│      ├─ Yes → dspy.Predict                                  │
│      └─ No                                                  │
│         │                                                   │
│         ├─ Need reasoning/thinking? → dspy.ChainOfThought   │
│         │                                                   │
│         ├─ Need to use tools? → dspy.ReAct                  │
│         │                                                   │
│         └─ Multiple steps? → Build custom dspy.Module       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎓 Practice Exercises

### Exercise 1: Basic Prediction
```python
# Create a sentiment analyzer
sentiment = dspy.Predict("text -> sentiment")
result = sentiment(text="I love DSPy!")
print(result.sentiment)
```

### Exercise 2: Chain of Thought
```python
# Solve a math problem with reasoning
math_solver = dspy.ChainOfThought("question -> answer")
result = math_solver(question="If I have 5 apples and eat 2, then buy 3 more, how many do I have?")
print(result.rationale)  # Read the thinking
print(result.answer)
```

### Exercise 3: Classification with Types
```python
from typing import Literal

class EmailCategory(dspy.Signature):
    """Categorize an email."""
    subject = dspy.InputField()
    body = dspy.InputField()
    category = Literal["work", "personal", "spam"] = dspy.OutputField()

classifier = dspy.Predict(EmailCategory)
result = classifier(
    subject="Meeting Tomorrow",
    body="Let's discuss the project roadmap."
)
```

---

## 📖 Next Steps

1. **Run the examples**: `python examples/basics.py`
2. **Read the full tutorial**: `dspy-basics-tutorial.md`
3. **Build a RAG app**: Try the RAG tutorial
4. **Learn optimization**: Use teleprompters to improve performance

---

## 📚 Files Created

| File | Purpose |
|------|---------|
| `dspy-basics-tutorial.md` | Complete tutorial |
| `examples/basics.py` | Runnable examples |
| `DSPY_QUICKSTART.md` | This file |

---

## 🔑 Key Takeaways

- **Signatures** = Declarative input/output (WHAT)
- **Modules** = Strategies for using LMs (HOW)
- **LMs** = Configurable backends (ENGINE)
- **Custom Modules** = Compose multiple steps
- **Optimization** = Auto-improve performance

---

**Happy DSPy coding! 🚀**
