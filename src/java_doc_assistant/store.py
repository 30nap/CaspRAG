"""لایه‌ی ذخیره‌سازی برداری.

اینترفیس VectorStore جدا از پیاده‌سازی Chroma تعریف شده تا بعداً بتوان
دیتابیس برداری را بدون تغییر منطق اصلی عوض کرد.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    """چانک بازیابی‌شده همراه متادیتای ارجاع به منبع."""

    document: str
    metadata: dict
    distance: float | None = None

    @property
    def source_ref(self) -> str:
        return (
            f"{self.metadata.get('file_path', '?')}"
            f" (lines {self.metadata.get('start_line', '?')}-{self.metadata.get('end_line', '?')})"
        )


class VectorStore(ABC):
    """اینترفیس دیتابیس برداری — پیاده‌سازی پیش‌فرض: Chroma."""

    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None: ...

    @abstractmethod
    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]: ...

    @abstractmethod
    def all_metadatas(self) -> list[dict]:
        """همه‌ی متادیتاها — برای پاسخ‌های آماری بدون فراخوانی مدل."""

    @abstractmethod
    def get_by_metadata(self, where: dict) -> list[RetrievedChunk]: ...

    @abstractmethod
    def delete_by_metadata(self, where: dict) -> None: ...

    @abstractmethod
    def count(self) -> int: ...


class ChromaStore(VectorStore):
    def __init__(self, path: str, collection: str):
        import chromadb
        from chromadb.config import Settings

        # telemetry خاموش: هیچ اتصال شبکه‌ای خارج از سرور داخلی مجاز نیست
        self._client = chromadb.PersistentClient(
            path=path, settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, ids, documents, embeddings, metadatas) -> None:
        # Chroma برای درخواست‌های خیلی بزرگ محدودیت دارد؛ دسته‌دسته ارسال می‌کنیم
        batch = 200
        for i in range(0, len(ids), batch):
            self._collection.upsert(
                ids=ids[i : i + batch],
                documents=documents[i : i + batch],
                embeddings=embeddings[i : i + batch],
                metadatas=metadatas[i : i + batch],
            )

    def query(self, embedding, top_k) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            chunks.append(RetrievedChunk(document=doc, metadata=meta, distance=dist))
        return chunks

    def all_metadatas(self) -> list[dict]:
        result = self._collection.get(include=["metadatas"])
        return list(result["metadatas"] or [])

    def get_by_metadata(self, where: dict) -> list[RetrievedChunk]:
        result = self._collection.get(where=where, include=["documents", "metadatas"])
        return [
            RetrievedChunk(document=doc, metadata=meta)
            for doc, meta in zip(result["documents"], result["metadatas"])
        ]

    def delete_by_metadata(self, where: dict) -> None:
        self._collection.delete(where=where)

    def count(self) -> int:
        return self._collection.count()
