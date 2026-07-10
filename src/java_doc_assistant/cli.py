"""رابط خط فرمان java-doc-assistant.

دستورها:
  index <path>                ایندکس کردن یک ریپازیتوری/پوشه‌ی جاوا
  ask "<question>"            پرسش؛ پیش‌فرض چاپ در ترمینال، با --save ذخیره در فایل
  docgen --package/--class    تولید مستند Markdown (همیشه فایل می‌سازد)

این ابزار فقط-خواندنی است: کدبیس را هرگز تغییر نمی‌دهد، دستور shell اجرا نمی‌کند
و تنها خروجی‌های آن دایرکتوری ایندکس Chroma و فایل‌های Markdown تولیدی هستند.
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
        embedder=OllamaEmbeddingClient(cfg.base_url, cfg.embedding_model, cfg.timeout_seconds),
        chat=OllamaChatClient(cfg.base_url, cfg.chat_model, cfg.timeout_seconds),
        top_k=cfg.top_k,
    )


def _load_config_or_exit(config_path: str | None) -> Config:
    try:
        return load_config(config_path)
    except ConfigError as exc:
        click.echo(f"خطا: {exc}", err=True)
        sys.exit(1)


def _write_markdown(path: Path, title: str, answer: Answer) -> None:
    if path.suffix.lower() != ".md":
        raise click.ClickException(
            f"خروجی فقط به‌صورت فایل .md ذخیره می‌شود، نه: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"# {title}", "", answer.text]
    if answer.sources:
        parts += ["", "---", "", "## منابع بازیابی‌شده", ""]
        parts += [f"- `{src}`" for src in answer.sources]
    parts += [
        "",
        f"*تولیدشده توسط java-doc-assistant در {datetime.now():%Y-%m-%d %H:%M}*",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def _print_answer(answer: Answer) -> None:
    click.echo(answer.text)
    if answer.sources:
        click.echo("\n--- منابع بازیابی‌شده ---")
        seen = set()
        for src in answer.sources:
            if src not in seen:
                seen.add(src)
                click.echo(f"  - {src}")


@click.group()
def main() -> None:
    """دستیار فقط-خواندنی پرسش‌وپاسخ و مستندسازی برای کدبیس‌های جاوا (RAG لوکال)."""
    click.echo(BANNER)


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--config", "config_path", default=None, help="مسیر config.yaml")
def index(path: Path, config_path: str | None) -> None:
    """ایندکس کردن فایل‌های .java یک ریپازیتوری یا پوشه."""
    cfg = _load_config_or_exit(config_path)
    store = _build_store(cfg)
    embedder = OllamaEmbeddingClient(cfg.base_url, cfg.embedding_model, cfg.timeout_seconds)
    chunker = JavaChunker(max_chunk_chars=cfg.max_chunk_chars)

    click.echo(f"ایندکس کردن {path} ...")
    try:
        result = index_codebase(
            root=path,
            chunker=chunker,
            embedder=embedder,
            store=store,
            progress=lambda msg: click.echo(msg),
        )
    except LLMServerError as exc:
        click.echo(f"خطا: {exc}", err=True)
        sys.exit(2)
    click.echo(
        f"\nتمام شد: {result.files_indexed} فایل، {result.chunks_indexed} چانک ایندکس شد"
        + (f"، {result.files_failed} فایل ناموفق" if result.files_failed else "")
        + f"\nایندکس در: {cfg.chroma_path}"
    )


@main.command()
@click.argument("question")
@click.option("--save", is_flag=True, default=False,
              help="ذخیره‌ی پاسخ به‌صورت فایل Markdown به‌جای چاپ صرف در ترمینال")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="مسیر فایل خروجی (فقط همراه --save؛ پیش‌فرض داخل output.docs_dir)")
@click.option("-k", "top_k", type=int, default=None, help="تعداد چانک‌های بازیابی‌شده")
@click.option("--config", "config_path", default=None, help="مسیر config.yaml")
def ask(question: str, save: bool, out_path: Path | None, top_k: int | None,
        config_path: str | None) -> None:
    """پرسش درباره‌ی کدبیس ایندکس‌شده؛ خروجی پیش‌فرض چاپ در ترمینال است."""
    if out_path is not None and not save:
        raise click.UsageError("--out فقط همراه --save معنا دارد.")
    cfg = _load_config_or_exit(config_path)
    store = _build_store(cfg)

    # سوالات آماری ساده بدون فراخوانی مدل، مستقیم از متادیتای ایندکس پاسخ می‌گیرند
    statistical = try_answer_statistical(question, store)
    if statistical is not None:
        click.echo(statistical)
        return

    pipeline = RagPipeline(
        store=store,
        embedder=OllamaEmbeddingClient(cfg.base_url, cfg.embedding_model, cfg.timeout_seconds),
        chat=OllamaChatClient(cfg.base_url, cfg.chat_model, cfg.timeout_seconds),
        top_k=top_k or cfg.top_k,
    )
    try:
        answer = pipeline.ask(question)
    except LLMServerError as exc:
        click.echo(f"خطا: {exc}", err=True)
        sys.exit(2)

    if save:
        target = out_path or (
            Path(cfg.docs_dir) / f"ask-{datetime.now():%Y%m%d-%H%M%S}.md"
        )
        _write_markdown(target, f"پاسخ: {question}", answer)
        click.echo(f"پاسخ در فایل ذخیره شد: {target}")
    else:
        _print_answer(answer)


@main.command()
@click.option("--package", "package", default=None, help="نام کامل پکیج (مثل com.example.batch)")
@click.option("--class", "class_name", default=None, help="نام کلاس (ساده یا کامل)")
@click.option("-o", "--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="مسیر فایل Markdown خروجی (پیش‌فرض داخل output.docs_dir)")
@click.option("--config", "config_path", default=None, help="مسیر config.yaml")
def docgen(package: str | None, class_name: str | None, out_path: Path | None,
           config_path: str | None) -> None:
    """تولید مستند Markdown برای یک پکیج یا کلاس (همیشه فایل می‌سازد)."""
    if bool(package) == bool(class_name):
        raise click.UsageError("دقیقاً یکی از --package یا --class را مشخص کنید.")
    cfg = _load_config_or_exit(config_path)
    pipeline = _build_pipeline(cfg)

    target = package or class_name
    chunks = (
        pipeline.chunks_for_package(package) if package
        else pipeline.chunks_for_class(class_name)
    )
    if not chunks:
        click.echo(f"هیچ چانکی برای «{target}» در ایندکس پیدا نشد.", err=True)
        sys.exit(1)

    click.echo(f"تولید مستند برای «{target}» با {len(chunks)} چانک ...")
    try:
        answer = pipeline.docgen(target, chunks)
    except LLMServerError as exc:
        click.echo(f"خطا: {exc}", err=True)
        sys.exit(2)

    safe_name = target.replace(".", "_")
    final_path = out_path or (Path(cfg.docs_dir) / f"doc-{safe_name}.md")
    _write_markdown(final_path, f"مستند {target}", answer)
    click.echo(f"مستند ذخیره شد: {final_path}")


if __name__ == "__main__":
    main()
