# Casp RAG — java-doc-assistant

A **read-only** Q&A and documentation assistant for Java codebases (Spring Boot / Spring Batch), built on a fully local RAG pipeline.

- Structural chunking with `tree-sitter-java` at the **whole class/method** level (each chunk carries its javadoc and the enclosing class signature as context)
- Vector storage in **Chroma** (local, persistent)
- Embedding and answer generation through an internal **Ollama-compatible** server (`/api/embed` and `/api/chat`) — the server URL and both model names are configured only in `config.yaml`, never hardcoded
- Answers are always in **Persian** and always cite the source file path and line range

## Security constraints (designed for banking code)

- The tool only **reads** the codebase; it has no file write/edit, apply_diff, or shell execution capability.
- The only write locations are the Chroma index directory (`chroma.path`) and generated Markdown output (`output.docs_dir`).
- The only network destination is `server.base_url` from the config; Chroma telemetry is disabled as well.

## Installation

```bash
python3 -m pip install .
```

(Requires Python 3.11+)

## Configuration

Edit `config.yaml` (a sample is provided at the repository root):

```yaml
server:
  base_url: "http://your-internal-server:11434"
models:
  chat: "qwen2.5-coder:32b"       # answer-generation model
  embedding: "nomic-embed-text"   # embedding model (separate from the chat model)
chroma:
  path: "./.java-doc-index"
```

Config path resolution order: `--config` flag > `JAVA_DOC_ASSISTANT_CONFIG` environment variable > `./config.yaml`.

## Usage

```bash
# 1) Index a Java repository
java-doc-assistant index /path/to/java/project

# 2) Ask a question — output is printed to the terminal by default, no file is created
java-doc-assistant ask "متد transfer در AccountService چیکار می‌کنه؟"

# Simple statistical questions are answered directly from the index, without calling the LLM
java-doc-assistant ask "تعداد کلاس‌های پروژه چقدره؟"
java-doc-assistant ask "لیست پکیج‌ها"

# Save the answer as a Markdown file only with the explicit --save flag
java-doc-assistant ask "منطق batch را توضیح بده" --save --out report.md

# 3) Generate Markdown documentation for a package or class (always writes a file)
java-doc-assistant docgen --package com.example.bank.batch
java-doc-assistant docgen --class AccountService -o docs/account-service.md
```

## Testing

Tests run against the small sample project in `sample_project/` using a mock Ollama-compatible server (no real model needed):

```bash
python3 -m pip install pytest
python3 -m pytest tests/ -v
```

For manual experimentation without a real server, `python3 tests/mock_ollama.py` starts a mock server on port 11434.

## Code structure

```
src/java_doc_assistant/
  cli.py            index / ask / docgen commands
  config.py         config.yaml loading (no server URL or model name is hardcoded)
  parser.py         tree-sitter chunking (class/method + javadoc + class signature)
  indexer.py        walk .java files → chunks → embeddings → Chroma
  store.py          VectorStore interface + Chroma implementation (swappable)
  ollama_client.py  EmbeddingClient/ChatClient interfaces + Ollama implementation (swappable)
  rag.py            retrieval and prompt building for ask / docgen
  stats.py          rule-based statistical answers without the LLM
  prompts.py        Persian system prompt and question templates
```

The vector store and model client layers sit behind interfaces (ABCs); swapping out Chroma or the model backend requires no changes to the core logic (`rag.py`, `indexer.py`, `cli.py`).
