# DSPy Basics - Learning Resources

This directory contains comprehensive materials for learning DSPy from scratch.

## 📁 Files Overview

| File | Description | Purpose |
|------|-------------|---------|
| `dspy-basics-tutorial.md` | Complete beginner's tutorial | Deep dive into DSPy concepts |
| `DSPY_QUICKSTART.md` | 5-minute quick start | Get started immediately |
| `examples/basics.py` | Runnable code examples | Hands-on practice |
| `dspy-research.md` | Research notes | Quick reference |

---

## 🚀 Recommended Learning Path

### 1. Start Here: Quick Start (5 minutes)
```bash
# Read the quick start guide
cat DSPY_QUICKSTART.md
```

You'll learn:
- ✅ DSPy installation
- ✅ Basic configuration
- ✅ Your first DSPy program
- ✅ Core concepts overview

### 2. Deep Dive: Full Tutorial (30 minutes)
```bash
# Read the complete tutorial
cat dspy-basics-tutorial.md
```

You'll learn:
- ✅ Signatures in detail
- ✅ All built-in modules
- ✅ Custom module creation
- ✅ Optimization techniques
- ✅ Evaluation methods

### 3. Practice: Code Examples (30 minutes)
```bash
# Run the examples
cd examples
python basics.py
```

You'll practice:
- ✅ Basic prediction
- ✅ Chain of thought
- ✅ Sentiment analysis
- ✅ Custom modules
- ✅ Module comparison

---

## 🔧 Setup

### 1. Install DSPy
```bash
pip install dspy-ai
```

### 2. Set Your API Key
```bash
# Option A: Environment variable (recommended)
export OPENAI_API_KEY="sk-..."

# Option B: .env file
echo "OPENAI_API_KEY=sk-..." > .env
```

### 3. Run Examples
```bash
python examples/basics.py
```

---

## 📚 Concepts by Difficulty

### Beginner (Start Here)
- ✅ Installation & setup
- ✅ Basic signatures
- ✅ `dspy.Predict` module
- ✅ Input/output fields

### Intermediate
- ✅ `dspy.ChainOfThought` module
- ✅ Type constraints with `Literal`
- ✅ Compact syntax
- ✅ Multiple outputs

### Advanced
- ✅ Custom modules
- ✅ `dspy.ReAct` agents
- ✅ Optimization (teleprompters)
- ✅ Evaluation frameworks

---

## 💡 Common Use Cases

### 1. Question Answering
```python
qa = dspy.Predict("question -> answer")
result = qa(question="What is DSPy?")
```

### 2. Text Classification
```python
classifier = dspy.Predict("text -> category")
result = classifier(text="This is amazing!")
```

### 3. Summarization
```python
summarizer = dspy.ChainOfThought("long_text -> summary")
result = summarizer(long_text="...")
```

### 4. Retrieval-Augmented Generation (RAG)
```python
class RAG(dspy.Module):
    def forward(self, question):
        context = retrieve(question)
        return generate(question=question, context=context)
```

---

## 🎯 Exercises

After reading the tutorial, try these:

1. **Exercise 1**: Create a sentiment analyzer
   - Input: Product review text
   - Output: Positive/Negative/Neutral

2. **Exercise 2**: Build a math tutor
   - Use ChainOfThought
   - Show step-by-step solutions

3. **Exercise 3**: Create a RAG pipeline
   - Retrieve from a knowledge base
   - Generate answers with context

4. **Exercise 4**: Build a custom module
   - Chain 2+ operations
   - Return multiple outputs

---

## 📖 Additional Resources

### Official Resources
- **DSPy Docs**: https://dspy.ai
- **DSPy GitHub**: https://github.com/stanfordnlp/dspy
- **Tutorials**: https://dspy.ai/tutorials

### Local Resources (Indexed)
- **DSPy Docs** (Nia): Source ID `27a1a73f-d5bb-475d-a0e6-3154e8a56386`
- **Context7 Library**: `/websites/dspy_ai`

### Searching DSPy Docs
```python
# Using Nia (if available)
nia_search(
    query="YOUR QUESTION",
    data_sources=["27a1a73f-d5bb-475d-a0e6-3154e8a56386"]
)

# Using Context7
context7_query_docs(
    libraryId="/websites/dspy_ai",
    query="YOUR QUESTION"
)
```

---

## 🔍 Troubleshooting

### Issue: API Key Not Found
```bash
# Set environment variable
export OPENAI_API_KEY="your-key-here"
```

### Issue: Module Not Found
```bash
# Reinstall DSPy
pip install --upgrade dspy-ai
```

### Issue: Context7 Not Available
```bash
# Context7 is a separate MCP server
# Follow setup instructions at:
# https://github.com/modelcontextprotocol
```

---

## 📝 Quick Reference

### Essential Imports
```python
import dspy
from dspy.teleprompt import BootstrapFewShot
from dspy.evaluate import Evaluate
```

### Basic Pattern
```python
# 1. Configure LM
lm = dspy.LM('openai/gpt-4o-mini', api_key='your-key')
dspy.configure(lm=lm)

# 2. Define signature
class MySig(dspy.Signature):
    """Description"""
    input: str = dspy.InputField()
    output: str = dspy.OutputField()

# 3. Create module
module = dspy.Predict(MySig)

# 4. Run
result = module(input="your input")
```

### Module Selection
- Simple tasks → `dspy.Predict`
- Reasoning → `dspy.ChainOfThought`
- Tools → `dspy.ReAct`
- Custom pipeline → `class dspy.Module`

---

## 🎓 Certificate of Completion

Complete these to master DSPy basics:

- [ ] Read Quick Start guide
- [ ] Read full Tutorial
- [ ] Run all examples
- [ ] Complete Exercise 1 (Sentiment)
- [ ] Complete Exercise 2 (Math Tutor)
- [ ] Complete Exercise 3 (RAG)
- [ ] Complete Exercise 4 (Custom Module)

---

**Happy Learning! 🚀**

For questions, refer to:
- DSPy Discord: https://discord.gg/K7SESdFk
- DSPy GitHub Discussions: https://github.com/stanfordnlp/dspy/discussions
