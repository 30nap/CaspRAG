"""casprag interactive mode — a coding-assistant-style prompt.

Running `casprag` with no subcommand opens this loop: any free text is a
question about the indexed codebase (Persian or English) and slash commands
(/index, /docgen, /save, ...) do the rest.

Terminal output is English; files written by /docgen and /save are Persian.
The same read-only guarantees as the rest of the tool apply here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from java_doc_assistant.config import Config
from java_doc_assistant.indexer import index_codebase
from java_doc_assistant.ollama_client import (
    LLMServerError,
    OllamaChatClient,
    OllamaEmbeddingClient,
)
from java_doc_assistant.parser import JavaChunker
from java_doc_assistant.rag import Answer, RagPipeline
from java_doc_assistant.stats import try_answer_statistical
from java_doc_assistant.store import ChromaStore

try:  # line editing/history in real terminals; absence is harmless
    import readline  # noqa: F401
except ImportError:
    pass

HELP_TEXT = """Commands:
  /index [path]      index a codebase (default: current folder)
  /docgen <target>   generate a Persian Markdown document for a package or class
  /save [path]       save the last answer as a Persian Markdown file
  /help              show this help
  /exit              quit

Any other text is asked as a question about the indexed codebase (Persian or
English). Answers are printed here in English; no file is written unless you
explicitly use /save or /docgen."""


class ReplSession:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._store = ChromaStore(path=cfg.chroma_path, collection=cfg.chroma_collection)
        self._embedder = OllamaEmbeddingClient(
            cfg.base_url, cfg.embedding_model, cfg.timeout_seconds
        )
        self._chat = OllamaChatClient(cfg.base_url, cfg.chat_model, cfg.timeout_seconds)
        self._pipeline = RagPipeline(
            store=self._store, embedder=self._embedder, chat=self._chat, top_k=cfg.top_k
        )
        self._last_question: str | None = None

    # ---------- main loop ----------

    def run(self) -> None:
        self._welcome()
        while True:
            try:
                line = input("casprag> ").strip()
            except (EOFError, KeyboardInterrupt):
                click.echo("\nBye!")
                return
            if not line:
                continue
            if line.startswith("/"):
                if not self._handle_command(line):
                    return
            else:
                self._handle_question(line)

    def _welcome(self) -> None:
        count = self._store.count()
        if count:
            click.echo(f"Index ready ({count} chunks). Type your question (Persian or English).")
        else:
            click.echo("The index is empty — run /index first.")
        click.echo("Help: /help — quit: /exit\n")

    # ---------- slash commands ----------

    def _handle_command(self, line: str) -> bool:
        """Run a slash command; returning False exits the loop."""
        command, _, arg = line.partition(" ")
        arg = arg.strip()
        if command in ("/exit", "/quit", "/q"):
            click.echo("Bye!")
            return False
        if command == "/help":
            click.echo(HELP_TEXT)
        elif command == "/index":
            self._do_index(arg or ".")
        elif command == "/docgen":
            self._do_docgen(arg)
        elif command == "/save":
            self._do_save(arg)
        else:
            click.echo(f"Unknown command: {command} — see /help")
        return True

    def _do_index(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.is_dir():
            click.echo(f"Folder not found: {path}")
            return
        click.echo(f"Indexing {path.resolve()} ...")
        try:
            result = index_codebase(
                root=path,
                chunker=JavaChunker(max_chunk_chars=self._cfg.max_chunk_chars),
                embedder=self._embedder,
                store=self._store,
                progress=lambda msg: click.echo(msg),
            )
        except LLMServerError as exc:
            click.echo(f"Error: {exc}")
            return
        click.echo(
            f"Done: {result.files_indexed} files, {result.chunks_indexed} chunks indexed"
            + (f", {result.files_failed} files failed" if result.files_failed else "")
        )

    def _do_docgen(self, target: str) -> None:
        if not target:
            click.echo("Usage: /docgen <package or class>  (e.g. /docgen com.example.batch)")
            return
        chunks = self._pipeline.chunks_for_package(target)
        if not chunks:
            chunks = self._pipeline.chunks_for_class(target)
        if not chunks:
            click.echo(f'No chunks found in the index for "{target}".')
            return
        click.echo(f'Generating documentation for "{target}" from {len(chunks)} chunks ...')
        try:
            answer = self._pipeline.docgen(target, chunks)
        except LLMServerError as exc:
            click.echo(f"Error: {exc}")
            return
        path = Path(self._cfg.docs_dir) / f"doc-{target.replace('.', '_')}.md"
        self._write_markdown(path, f"مستند {target}", answer)
        click.echo(f"Document saved to: {path}")

    def _do_save(self, path_str: str) -> None:
        if self._last_question is None:
            click.echo("Nothing to save yet; ask a question first.")
            return
        path = (
            Path(path_str)
            if path_str
            else Path(self._cfg.docs_dir) / f"ask-{datetime.now():%Y%m%d-%H%M%S}.md"
        )
        if path.suffix.lower() != ".md":
            click.echo(f"Output can only be saved as a .md file, not: {path}")
            return
        # saved files are Persian, so re-ask the last question in Persian
        click.echo("Generating the Persian answer for the file ...")
        try:
            answer = self._pipeline.ask(self._last_question, lang="fa")
        except LLMServerError as exc:
            click.echo(f"Error: {exc}")
            return
        self._write_markdown(path, f"پاسخ: {self._last_question}", answer)
        click.echo(f"Answer saved to: {path}")

    # ---------- free-text questions ----------

    def _handle_question(self, question: str) -> None:
        statistical = try_answer_statistical(question, self._store)
        if statistical is not None:
            click.echo(statistical)
            return
        try:
            answer = self._pipeline.ask(question, lang="en")
        except LLMServerError as exc:
            click.echo(f"Error: {exc}")
            return
        from java_doc_assistant.cli import _print_answer

        _print_answer(answer)
        click.echo()
        self._last_question = question

    # ---------- helpers ----------

    @staticmethod
    def _write_markdown(path: Path, title: str, answer: Answer) -> None:
        from java_doc_assistant.cli import _write_markdown

        _write_markdown(path, title, answer)


def run_repl(cfg: Config) -> None:
    ReplSession(cfg).run()
