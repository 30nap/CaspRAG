"""پایپ‌لاین ایندکس: پیمایش فایل‌های .java → چانک → embedding → ذخیره در Chroma.

این ماژول کدبیس را فقط می‌خواند. تنها محل نوشتن، دایرکتوری Chroma است.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from java_doc_assistant.ollama_client import EmbeddingClient
from java_doc_assistant.parser import CodeChunk, JavaChunker
from java_doc_assistant.store import VectorStore

SKIP_DIRS = {".git", "target", "build", "out", "node_modules", ".idea", ".gradle"}


@dataclass
class IndexResult:
    files_indexed: int
    files_failed: int
    chunks_indexed: int


def iter_java_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.java")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def index_codebase(
    root: Path,
    chunker: JavaChunker,
    embedder: EmbeddingClient,
    store: VectorStore,
    embed_batch_size: int = 32,
    progress: Callable[[str], None] | None = None,
) -> IndexResult:
    root = root.resolve()
    files_indexed = files_failed = chunks_indexed = 0
    pending: list[CodeChunk] = []

    def flush() -> None:
        nonlocal chunks_indexed
        if not pending:
            return
        embeddings = embedder.embed([c.embed_text for c in pending])
        store.upsert(
            ids=[c.chunk_id for c in pending],
            documents=[c.embed_text for c in pending],
            embeddings=embeddings,
            metadatas=[_metadata(c) for c in pending],
        )
        chunks_indexed += len(pending)
        pending.clear()

    for path in iter_java_files(root):
        rel_path = str(path.relative_to(root))
        try:
            source = path.read_bytes()
            file_chunks = chunker.chunk_file(source, rel_path)
        except Exception as exc:  # فایل خراب نباید کل ایندکس را متوقف کند
            files_failed += 1
            if progress:
                progress(f"  ! خطا در {rel_path}: {exc}")
            continue
        # چانک‌های قدیمی همین فایل حذف می‌شوند تا ایندکس مجدد باقی‌مانده نگذارد
        store.delete_by_metadata({"file_path": rel_path})
        pending.extend(file_chunks)
        files_indexed += 1
        if progress:
            progress(f"  + {rel_path} ({len(file_chunks)} چانک)")
        while len(pending) >= embed_batch_size:
            batch, rest = pending[:embed_batch_size], pending[embed_batch_size:]
            pending.clear()
            pending.extend(batch)
            flush()
            pending.extend(rest)

    flush()
    return IndexResult(files_indexed, files_failed, chunks_indexed)


def _metadata(chunk: CodeChunk) -> dict:
    return {
        "file_path": chunk.file_path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "package": chunk.package,
        "class_name": chunk.class_name,
        "method_name": chunk.method_name,
        "chunk_type": chunk.chunk_type,
        "class_signature": chunk.class_signature[:500],
        "has_javadoc": bool(chunk.javadoc),
    }
