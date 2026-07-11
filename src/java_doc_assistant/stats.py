"""پاسخ مستقیم به سوالات آماری ساده از روی متادیتای ایندکس — بدون فراخوانی مدل.

تشخیص با قانون ساده (regex روی کلیدواژه‌ها) انجام می‌شود، نه با حدس مدل؛
این هم سریع‌تر است و هم ریسک hallucination ندارد.
"""

from __future__ import annotations

import re

from java_doc_assistant.store import VectorStore

CLASS_LIKE_TYPES = {"class", "interface", "enum", "record", "annotation"}

# الگوهای فارسی و انگلیسی برای هر نوع سوال آماری
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("count_classes", re.compile(
        r"(تعداد|چند\s*تا|چندتا|چقدر|how\s+many|count).{0,30}(کلاس|class)"
        r"|(کلاس|class).{0,30}(چندتاست|چند\s*تاست|چندتا|چقدره)", re.IGNORECASE)),
    ("count_methods", re.compile(
        r"(تعداد|چند\s*تا|چندتا|چقدر|how\s+many|count).{0,30}(متد|method)"
        r"|(متد|method).{0,30}(چندتاست|چند\s*تاست|چندتا|چقدره)", re.IGNORECASE)),
    ("count_files", re.compile(
        r"(تعداد|چند\s*تا|چندتا|چقدر|how\s+many|count).{0,30}(فایل|file)"
        r"|(فایل|file).{0,30}(چندتاست|چند\s*تاست|چندتا|چقدره)", re.IGNORECASE)),
    ("count_packages", re.compile(
        r"(تعداد|چند\s*تا|چندتا|چقدر|how\s+many|count).{0,30}(پکیج|package)"
        r"|(پکیج|package).{0,30}(چندتاست|چند\s*تاست|چندتا|چقدره)", re.IGNORECASE)),
    ("list_packages", re.compile(
        r"(لیست|فهرست|list).{0,20}(پکیج|package)"
        r"|(پکیج|package)\s*ها.{0,10}(چیه|چیست|کدام|کدومان?)", re.IGNORECASE)),
    ("list_classes", re.compile(
        r"(لیست|فهرست|list).{0,20}(کلاس|class)"
        r"|(کلاس|class)\s*ها.{0,10}(چیه|چیست|کدام|کدومان?)", re.IGNORECASE)),
]


def try_answer_statistical(question: str, store: VectorStore) -> str | None:
    """اگر سوال آماری ساده باشد پاسخ فارسی برمی‌گرداند، وگرنه None."""
    matched = None
    for name, pattern in _PATTERNS:
        if pattern.search(question):
            matched = name
            break
    if matched is None:
        return None

    metadatas = store.all_metadatas()
    if not metadatas:
        return "The index is empty; index a codebase first with the index command."

    if matched == "count_classes":
        classes = _distinct_classes(metadatas)
        return f"Total indexed classes/types: {len(classes)} (computed directly from the index)"
    if matched == "count_methods":
        methods = {
            (m["file_path"], m["class_name"], m["method_name"], m["start_line"])
            for m in metadatas
            if m.get("chunk_type") in ("method", "constructor")
        }
        return f"Total indexed methods/constructors: {len(methods)} (computed directly from the index)"
    if matched == "count_files":
        files = {m.get("file_path") for m in metadatas}
        return f"Total indexed .java files: {len(files)} (computed directly from the index)"
    if matched == "count_packages":
        packages = _packages(metadatas)
        return f"Total packages: {len(packages)} (computed directly from the index)"
    if matched == "list_packages":
        packages = sorted(_packages(metadatas))
        listing = "\n".join(f"  - {p}" for p in packages)
        return f"Indexed packages ({len(packages)}):\n{listing}"
    if matched == "list_classes":
        classes = sorted(_distinct_classes(metadatas))
        listing = "\n".join(f"  - {pkg + '.' if pkg else ''}{cls}" for pkg, cls in classes)
        return f"Indexed classes/types ({len(classes)}):\n{listing}"
    return None


def _distinct_classes(metadatas: list[dict]) -> set[tuple[str, str]]:
    return {
        (m.get("package", ""), m.get("class_name", ""))
        for m in metadatas
        if m.get("chunk_type") in CLASS_LIKE_TYPES
    }


def _packages(metadatas: list[dict]) -> set[str]:
    return {m.get("package") or "(default package)" for m in metadatas}
