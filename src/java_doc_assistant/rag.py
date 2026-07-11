"""منطق اصلی پرسش‌وپاسخ و تولید مستند روی ایندکس.

این ماژول از اینترفیس‌های VectorStore / EmbeddingClient / ChatClient استفاده می‌کند
و به پیاده‌سازی خاصی (Chroma / Ollama) وابسته نیست.
"""

from __future__ import annotations

from dataclasses import dataclass

from java_doc_assistant.ollama_client import ChatClient, EmbeddingClient
from java_doc_assistant.prompts import (
    ASK_USER_TEMPLATE,
    DOCGEN_USER_TEMPLATE,
    format_context,
    system_prompt,
)
from java_doc_assistant.store import RetrievedChunk, VectorStore


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[str]  # «مسیر فایل (خطوط a-b)» برای هر چانک استفاده‌شده


class RagPipeline:
    def __init__(
        self,
        store: VectorStore,
        embedder: EmbeddingClient,
        chat: ChatClient,
        top_k: int = 8,
    ):
        self._store = store
        self._embedder = embedder
        self._chat = chat
        self._top_k = top_k

    def ask(self, question: str, lang: str = "en") -> Answer:
        """پاسخ به سوال؛ lang="en" برای ترمینال، lang="fa" برای ذخیره در فایل."""
        chunks = self._retrieve(question)
        if not chunks:
            return Answer(
                text="No relevant chunks found in the index. "
                "Make sure the codebase is indexed with the index command.",
                sources=[],
            )
        user_prompt = ASK_USER_TEMPLATE.format(
            context=format_context(chunks), question=question
        )
        text = self._chat.chat(system_prompt(lang), user_prompt)
        return Answer(text=text, sources=[c.source_ref for c in chunks])

    def docgen(self, target: str, chunks: list[RetrievedChunk]) -> Answer:
        """تولید مستند Markdown فارسی برای چانک‌های داده‌شده (پکیج یا کلاس)."""
        if not chunks:
            return Answer(
                text=f'No chunks found in the index for "{target}".',
                sources=[],
            )
        user_prompt = DOCGEN_USER_TEMPLATE.format(
            context=format_context(chunks), target=target
        )
        text = self._chat.chat(system_prompt("fa"), user_prompt)
        return Answer(text=text, sources=[c.source_ref for c in chunks])

    def chunks_for_package(self, package: str, limit: int = 60) -> list[RetrievedChunk]:
        """چانک‌های یک پکیج (یا زیرپکیج‌هایش) از روی متادیتا — بدون جست‌وجوی برداری."""
        exact = self._store.get_by_metadata({"package": package})
        if exact:
            return _cap_per_class(exact, limit)
        # زیرپکیج‌ها: Chroma فیلتر prefix ندارد؛ روی متادیتاها در پایتون فیلتر می‌کنیم
        prefix = package + "."
        all_meta = self._store.all_metadatas()
        sub_packages = sorted({
            m["package"] for m in all_meta
            if m.get("package") == package or str(m.get("package", "")).startswith(prefix)
        })
        result: list[RetrievedChunk] = []
        for pkg in sub_packages:
            result.extend(self._store.get_by_metadata({"package": pkg}))
        return _cap_per_class(result, limit)

    def chunks_for_class(self, class_name: str) -> list[RetrievedChunk]:
        chunks = self._store.get_by_metadata({"class_name": class_name})
        if chunks:
            return chunks
        # نام ساده‌ی کلاس‌های تودرتو (Inner) را هم پوشش بده
        all_meta = self._store.all_metadatas()
        matches = sorted({
            m["class_name"] for m in all_meta
            if str(m.get("class_name", "")).split(".")[-1] == class_name
        })
        result: list[RetrievedChunk] = []
        for name in matches:
            result.extend(self._store.get_by_metadata({"class_name": name}))
        return result

    def _retrieve(self, question: str) -> list[RetrievedChunk]:
        embedding = self._embedder.embed([question])[0]
        return self._store.query(embedding, self._top_k)


def _cap_per_class(chunks: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    """چانک‌ها را مرتب و به سقف limit محدود می‌کند تا پرامپت منفجر نشود."""
    ordered = sorted(
        chunks,
        key=lambda c: (
            c.metadata.get("file_path", ""),
            int(c.metadata.get("start_line", 0)),
        ),
    )
    return ordered[:limit]
