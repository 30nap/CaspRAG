# Casp RAG

A **read-only** Q&A and documentation assistant for Java codebases (Spring Boot / Spring Batch), built on a fully local RAG pipeline. Ships as the `casprag` command.

- Structural chunking with `tree-sitter-java` at the **whole class/method** level (each chunk carries its javadoc and the enclosing class signature as context)
- Vector storage in **Chroma** (local, persistent)
- Embedding and answer generation through an internal **Ollama-compatible** server (`/api/embed` and `/api/chat`) — the server URL and both model names are configured only in `config.yaml`, never hardcoded
- Questions can be asked in **Persian or English**; every answer cites the source file path and line range
- Language contract: **terminal output is English** (avoids broken RTL rendering in terminals); **generated Markdown files (`docgen`, `--save`, `/save`) are Persian**

## Security constraints (designed for banking code)

- The tool only **reads** the codebase; it has no file write/edit, apply_diff, or shell execution capability.
- The only write locations are the Chroma index directory (`chroma.path`) and generated Markdown output (`output.docs_dir`).
- The only network destination is `server.base_url` from the config; Chroma telemetry is disabled as well.

## Installation

```bash
python3 -m pip install .    # Windows: py -m pip install .
```

(Requires Python 3.11+)

### Windows: `casprag` is not recognized

pip installs `casprag.exe` into your Python `Scripts` folder; on many Windows setups (Microsoft Store Python, `--user` installs) that folder is not on `PATH` — pip prints a yellow warning like `WARNING: The script casprag.exe is installed in '...' which is not on PATH` during install.

Pick either fix:

1. **No PATH change needed** — run it as a module instead:

   ```bat
   py -m casprag
   py -m casprag ask "تعداد کلاس‌های پروژه چقدره؟"
   ```

2. **Add the Scripts folder to PATH** — find it, then add it to your user PATH and open a new terminal:

   ```bat
   py -c "import sysconfig; print(sysconfig.get_path('scripts'))"
   py -c "import site,os; print(os.path.join(site.USER_BASE,'Scripts'))"  &rem for --user installs
   ```

   Add the printed folder via *Settings → System → About → Advanced system settings → Environment Variables → Path*, then restart the terminal so `casprag` works directly.

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

### Interactive mode (recommended)

Run `casprag` with no subcommand inside your codebase folder to get an interactive prompt, similar to a coding-assistant CLI. Type a question directly, or use slash commands:

```
$ casprag

  ____                  ____      _    ____
 / ___|__ _ ___ _ __   |  _ \    / \  / ___|
| |   / _` / __| '_ \  | |_) |  / _ \| |  _
| |__| (_| \__ \ |_) | |  _ <  / ___ \ |_| |
 \____\__,_|___/ .__/  |_| \_\/_/   \_\____|
               |_|

casprag> /index .
casprag> متد transfer در AccountService چیکار می‌کنه؟
casprag> /docgen com.example.bank.batch
casprag> /exit
```

Slash commands: `/index [path]`, `/docgen <package|class>`, `/save [path]` (regenerates the last answer in Persian and saves it as Markdown), `/help`, `/exit`. Free text is treated as a question (Persian or English); answers are printed in the terminal in English and no file is written unless you explicitly `/save` or `/docgen`.

### One-shot commands

```bash
# 1) Index a Java repository
casprag index /path/to/java/project

# 2) Ask a question (Persian or English) — the answer is printed to the terminal
#    in English by default, no file is created
casprag ask "متد transfer در AccountService چیکار می‌کنه؟"
casprag ask "What does the transfer method do?"

# Simple statistical questions are answered directly from the index, without calling the LLM
casprag ask "تعداد کلاس‌های پروژه چقدره؟"
casprag ask "how many classes are there?"

# Save the answer as a Persian Markdown file only with the explicit --save flag
casprag ask "منطق batch را توضیح بده" --save --out report.md

# 3) Generate Persian Markdown documentation for a package or class (always writes a file)
casprag docgen --package com.example.bank.batch
casprag docgen --class AccountService -o docs/account-service.md
```

## Building a single-file executable

You can bundle casprag (with Python and all dependencies) into one self-contained binary using the provided PyInstaller spec:

```bash
python -m pip install . pyinstaller
pyinstaller casprag.spec
```

The result is `dist/casprag.exe` on Windows (`dist/casprag` on Linux/macOS, ~75 MB) — copy it anywhere and run it; no Python installation needed. Put a `config.yaml` next to it or pass `--config`. Note: PyInstaller does not cross-compile, so the Windows exe must be built **on Windows**.

Alternatively, the `Build single-file executable` GitHub Actions workflow builds both Windows and Linux binaries: run it from the repository's *Actions* tab (or push a `v*` tag) and download the `casprag-windows` artifact.

Two Windows notes: single-file PyInstaller apps unpack themselves to a temp folder on each start, so the first launch takes a few seconds; and some antivirus products flag unsigned PyInstaller binaries as suspicious — building the exe yourself (or via your own CI) is the usual mitigation.

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
  cli.py            casprag entry point: index / ask / docgen commands
  repl.py           interactive mode (free-text questions + slash commands)
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
