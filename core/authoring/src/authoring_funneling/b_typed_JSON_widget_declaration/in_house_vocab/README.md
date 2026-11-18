# In-House Python Function Vocabulary & Registry Guide

Status: Authoritative developer guide for authoring, registering, and authorizing custom Python operations for `JSONfnchainTM` and Layer C JSONic widgets.

---

## 1. Overview & Architectural Boundaries

In accordance with **Philosophy 3 (The Single-Envelope Doctrine)**, public JSONic widget creators compose functions from two approved sources:
1. **The Custom Python Ops Catalogue** (this library of pure transforms and async utilities).
2. **The Vendor Hub Ops Catalogue** (Layer A Gateway-adapted operations: LLMs, embeddings, media).

This directory (`in_house_vocab/`) is the designated home for in-house Python functions approved for use in JSON function chains.

---

## 2. Function Categories & Authoring Guidelines

### Category A: Pure In-Memory Transforms
- **Execution Guarantee**: Must be pure, deterministic, and free of side-effects.
- **Performance**: Must execute in $<1$ms in-process.
- **Example Modules**:
  - `pure_text.py`: String manipulation, regex extraction, templating.
  - `pure_math.py`: Arithmetic, statistical aggregations, geometry.
  - `pure_data.py`: Object reshaping, key extraction, collection filtering.

#### Authoring Template:
```python
from bindings2bindingsTM import Dict, Str, List

def register_custom_text_ops(vocab):
    vocab.register(
        name="text.slugify",
        inputs=Dict({"text": Str}),
        output=Dict({"slug": Str}),
        fn=lambda args, ctx: {"slug": args["text"].strip().lower().replace(" ", "-")},
        version="1.0"
    )
```

### Category B: Asynchronous Waiting & Polling Utilities
- **Execution Guarantee**: Safe to wait on external network I/O because flows execute on dedicated `QUEUE_ASYNCWORK` workers.
- **Catalogued Operations**:
  - `asyncwork.await_result`: Bounded synchronous wait on an `AsyncWorkHandle` until done or deadline expires.
  - `asyncwork.poll`: Point-seek inspection returning current execution status and latest progress percentage.

---

## 3. Registration Contract (`vocab_hub.py`)

All in-house functions are compiled into `THINKUMENT_GLOBAL_VOCAB` in `vocab_hub.py`:
1. Call `FunctionVocab.register(name, inputs, output, fn, version)`.
2. Input and output schemas must be finite structural schemas normalized by `bindings2bindingsTM`.
3. Names must follow reverse-domain or dot-separated category naming (e.g. `text.*`, `math.*`, `asyncwork.*`).

---

## 4. Safety & Security Rules

1. **No Direct Database Writes**: Functions must not execute direct ORM writes. All state persistence occurs through widget outputs (`strict_outputs_v1`) or `storagics`.
2. **No Unchecked Concurrency**: Do not spawn uncontrolled threads or subprocesses inside vocabulary callables.
3. **No Dynamic Code Evaluation**: Never use `eval()`, `exec()`, or dynamic import inside a vocabulary function.
