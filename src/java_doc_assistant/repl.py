"""حالت تعاملی casprag — شبیه یک دستیار خط فرمانی.

اجرای `casprag` بدون زیر‌دستور این حلقه را باز می‌کند:
هر متن آزاد یک سوال درباره‌ی کدبیس ایندکس‌شده است و دستورهای اسلشی
(/index، /docgen، /save، ...) کارهای دیگر را انجام می‌دهند.
همان محدودیت‌های فقط-خواندنی بقیه‌ی ابزار اینجا هم برقرار است.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from java_doc_assistant.config import Config
from java_doc_assistant.display import echo, prompt_text
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

try:  # تاریخچه و ویرایش خط در ترمینال‌های واقعی؛ نبودنش مشکلی ایجاد نمی‌کند
    import readline  # noqa: F401
except ImportError:
    pass

HELP_TEXT = """دستورها:
  /index [path]      ایندکس کردن کدبیس (پیش‌فرض: پوشه‌ی فعلی)
  /docgen <target>   تولید مستند Markdown برای یک پکیج یا کلاس
  /save [path]       ذخیره‌ی آخرین پاسخ به‌صورت فایل Markdown
  /help              نمایش همین راهنما
  /exit              خروج

هر متن دیگری به‌عنوان سوال درباره‌ی کدبیس ایندکس‌شده پرسیده می‌شود؛
پاسخ همین‌جا چاپ می‌شود و فایلی ساخته نمی‌شود مگر خودتان /save بزنید."""


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
        self._last_answer: Answer | None = None

    # ---------- حلقه‌ی اصلی ----------

    def run(self) -> None:
        self._welcome()
        while True:
            try:
                line = input(prompt_text("casprag> ")).strip()
            except (EOFError, KeyboardInterrupt):
                echo("\nخداحافظ!")
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
            echo(f"ایندکس آماده است ({count} چانک). سوال‌تان را بنویسید.")
        else:
            echo("ایندکس خالی است — اول با /index کدبیس را ایندکس کنید.")
        echo("راهنما: /help — خروج: /exit\n")

    # ---------- دستورهای اسلشی ----------

    def _handle_command(self, line: str) -> bool:
        """اجرای دستور اسلشی؛ برگرداندن False یعنی خروج از حلقه."""
        command, _, arg = line.partition(" ")
        arg = arg.strip()
        if command in ("/exit", "/quit", "/q"):
            echo("خداحافظ!")
            return False
        if command == "/help":
            echo(HELP_TEXT)
        elif command == "/index":
            self._do_index(arg or ".")
        elif command == "/docgen":
            self._do_docgen(arg)
        elif command == "/save":
            self._do_save(arg)
        else:
            echo(f"دستور ناشناخته: {command} — راهنما: /help")
        return True

    def _do_index(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.is_dir():
            echo(f"پوشه پیدا نشد: {path}")
            return
        echo(f"ایندکس کردن {path.resolve()} ...")
        try:
            result = index_codebase(
                root=path,
                chunker=JavaChunker(max_chunk_chars=self._cfg.max_chunk_chars),
                embedder=self._embedder,
                store=self._store,
                progress=lambda msg: echo(msg),
            )
        except LLMServerError as exc:
            echo(f"خطا: {exc}")
            return
        echo(
            f"تمام شد: {result.files_indexed} فایل، {result.chunks_indexed} چانک ایندکس شد"
            + (f"، {result.files_failed} فایل ناموفق" if result.files_failed else "")
        )

    def _do_docgen(self, target: str) -> None:
        if not target:
            echo("استفاده: /docgen <package یا class>  (مثال: /docgen com.example.batch)")
            return
        chunks = self._pipeline.chunks_for_package(target)
        if not chunks:
            chunks = self._pipeline.chunks_for_class(target)
        if not chunks:
            echo(f"هیچ چانکی برای «{target}» در ایندکس پیدا نشد.")
            return
        echo(f"تولید مستند برای «{target}» با {len(chunks)} چانک ...")
        try:
            answer = self._pipeline.docgen(target, chunks)
        except LLMServerError as exc:
            echo(f"خطا: {exc}")
            return
        path = Path(self._cfg.docs_dir) / f"doc-{target.replace('.', '_')}.md"
        self._write_markdown(path, f"مستند {target}", answer)
        echo(f"مستند ذخیره شد: {path}")

    def _do_save(self, path_str: str) -> None:
        if self._last_answer is None:
            echo("هنوز پاسخی برای ذخیره وجود ندارد؛ اول یک سوال بپرسید.")
            return
        path = (
            Path(path_str)
            if path_str
            else Path(self._cfg.docs_dir) / f"ask-{datetime.now():%Y%m%d-%H%M%S}.md"
        )
        if path.suffix.lower() != ".md":
            echo(f"خروجی فقط به‌صورت فایل .md ذخیره می‌شود، نه: {path}")
            return
        self._write_markdown(path, f"پاسخ: {self._last_question}", self._last_answer)
        echo(f"پاسخ در فایل ذخیره شد: {path}")

    # ---------- سوال آزاد ----------

    def _handle_question(self, question: str) -> None:
        statistical = try_answer_statistical(question, self._store)
        if statistical is not None:
            echo(statistical)
            return
        try:
            answer = self._pipeline.ask(question)
        except LLMServerError as exc:
            echo(f"خطا: {exc}")
            return
        from java_doc_assistant.cli import _print_answer

        _print_answer(answer)
        echo()
        self._last_question, self._last_answer = question, answer

    # ---------- کمکی ----------

    @staticmethod
    def _write_markdown(path: Path, title: str, answer: Answer) -> None:
        from java_doc_assistant.cli import _write_markdown

        _write_markdown(path, title, answer)


def run_repl(cfg: Config) -> None:
    ReplSession(cfg).run()
