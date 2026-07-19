"""casprag command-line interface.

Running with no subcommand opens the interactive mode (REPL): type a question
directly (Persian or English) or use slash commands like /index and /docgen.

Subcommands:
  index <path>                index a Java repository/folder
  ask "<question>"            ask a question; prints to the terminal by default,
                              --save writes the answer to a Persian Markdown file
  docgen --package/--class    generate a Persian Markdown document (always a file)

Terminal output is English; generated Markdown files are Persian.

This tool is read-only: it never modifies the codebase, never runs shell
commands, and its only outputs are the Chroma index directory and generated
Markdown files.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click

from java_doc_assistant.config import Config, ConfigError, load_config
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

BANNER = r"""
  ____                  ____      _    ____
 / ___|__ _ ___ _ __   |  _ \    / \  / ___|
| |   / _` / __| '_ \  | |_) |  / _ \| |  _
| |__| (_| \__ \ |_) | |  _ <  / ___ \ |_| |
 \____\__,_|___/ .__/  |_| \_\/_/   \_\____|
               |_|
"""


def _build_store(cfg: Config) -> ChromaStore:
    return ChromaStore(path=cfg.chroma_path, collection=cfg.chroma_collection)


def _build_pipeline(cfg: Config) -> RagPipeline:
    return RagPipeline(
        store=_build_store(cfg),
        embedder=OllamaEmbeddingClient(cfg.embedding_base_url, cfg.embedding_model, cfg.timeout_seconds),
        chat=OllamaChatClient(cfg.chat_base_url, cfg.chat_model, cfg.timeout_seconds),
        top_k=cfg.top_k,
    )


def _load_config_or_exit(config_path: str | None) -> Config:
    try:
        return load_config(config_path)
    except ConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _write_markdown(path: Path, title: str, answer: Answer) -> None:
    if path.suffix.lower() != ".md":
        raise click.ClickException(
            f"Output can only be saved as a .md file, not: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"# {title}", "", answer.text]
    if answer.sources:
        parts += ["", "---", "", "## منابع بازیابی‌شده", ""]
        parts += [f"- `{src}`" for src in answer.sources]
    parts += [
        "",
        f"*تولیدشده توسط casprag در {datetime.now():%Y-%m-%d %H:%M}*",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def _print_answer(answer: Answer) -> None:
    click.echo(answer.text)
    if answer.sources:
        click.echo("\n--- Sources ---")
        seen = set()
        for src in answer.sources:
            if src not in seen:
                seen.add(src)
                click.echo(f"  - {src}")


@click.group(invoke_without_command=True)
@click.option("--config", "config_path", default=None, help="path to config.yaml")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """Read-only Q&A and documentation assistant for Java codebases (local RAG).

    Run with no subcommand to open the interactive mode.
    """
    click.echo(BANNER)
    if ctx.invoked_subcommand is None:
        from java_doc_assistant.repl import run_repl

        run_repl(_load_config_or_exit(config_path))


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--config", "config_path", default=None, help="path to config.yaml")
def index(path: Path, config_path: str | None) -> None:
    """Index the .java files of a repository or folder."""
    cfg = _load_config_or_exit(config_path)
    store = _build_store(cfg)
    embedder = OllamaEmbeddingClient(cfg.embedding_base_url, cfg.embedding_model, cfg.timeout_seconds)
    chunker = JavaChunker(max_chunk_chars=cfg.max_chunk_chars)

    click.echo(f"Indexing {path} ...")
    try:
        result = index_codebase(
            root=path,
            chunker=chunker,
            embedder=embedder,
            store=store,
            progress=lambda msg: click.echo(msg),
        )
    except LLMServerError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)
    click.echo(
        f"\nDone: {result.files_indexed} files, {result.chunks_indexed} chunks indexed"
        + (f", {result.files_failed} files failed" if result.files_failed else "")
        + f"\nIndex stored at: {cfg.chroma_path}"
    )


@main.command()
@click.argument("question")
@click.option("--save", is_flag=True, default=False,
              help="save the answer as a Persian Markdown file instead of printing it")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="output file path (only with --save; defaults into output.docs_dir)")
@click.option("-k", "top_k", type=int, default=None, help="number of chunks to retrieve")
@click.option("--config", "config_path", default=None, help="path to config.yaml")
def ask(question: str, save: bool, out_path: Path | None, top_k: int | None,
        config_path: str | None) -> None:
    """Ask about the indexed codebase (Persian or English); prints to the terminal by default."""
    if out_path is not None and not save:
        raise click.UsageError("--out only makes sense together with --save.")
    cfg = _load_config_or_exit(config_path)
    store = _build_store(cfg)

    # simple statistical questions are answered directly from index metadata, no LLM call
    statistical = try_answer_statistical(question, store)
    if statistical is not None:
        click.echo(statistical)
        return

    pipeline = RagPipeline(
        store=store,
        embedder=OllamaEmbeddingClient(cfg.embedding_base_url, cfg.embedding_model, cfg.timeout_seconds),
        chat=OllamaChatClient(cfg.chat_base_url, cfg.chat_model, cfg.timeout_seconds),
        top_k=top_k or cfg.top_k,
    )
    try:
        # terminal answers are English; answers saved to a file are Persian
        answer = pipeline.ask(question, lang="fa" if save else "en")
    except LLMServerError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if save:
        target = out_path or (
            Path(cfg.docs_dir) / f"ask-{datetime.now():%Y%m%d-%H%M%S}.md"
        )
        _write_markdown(target, f"پاسخ: {question}", answer)
        click.echo(f"Answer saved to: {target}")
    else:
        _print_answer(answer)


@main.command()
@click.option("--package", "package", default=None,
              help="fully qualified package name (e.g. com.example.batch)")
@click.option("--class", "class_name", default=None, help="class name (simple or qualified)")
@click.option("-o", "--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="output Markdown file path (defaults into output.docs_dir)")
@click.option("--config", "config_path", default=None, help="path to config.yaml")
def docgen(package: str | None, class_name: str | None, out_path: Path | None,
           config_path: str | None) -> None:
    """Generate a Persian Markdown document for a package or class (always writes a file)."""
    if bool(package) == bool(class_name):
        raise click.UsageError("Specify exactly one of --package or --class.")
    cfg = _load_config_or_exit(config_path)
    pipeline = _build_pipeline(cfg)

    target = package or class_name
    chunks = (
        pipeline.chunks_for_package(package) if package
        else pipeline.chunks_for_class(class_name)
    )
    if not chunks:
        click.echo(f'No chunks found in the index for "{target}".', err=True)
        sys.exit(1)

    click.echo(f'Generating documentation for "{target}" from {len(chunks)} chunks ...')
    try:
        answer = pipeline.docgen(target, chunks)
    except LLMServerError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    safe_name = target.replace(".", "_")
    final_path = out_path or (Path(cfg.docs_dir) / f"doc-{safe_name}.md")
    _write_markdown(final_path, f"مستند {target}", answer)
    click.echo(f"Document saved to: {final_path}")


if __name__ == "__main__":
    main()
