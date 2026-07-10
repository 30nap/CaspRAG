"""چانک‌سازی ساختاری فایل‌های جاوا با tree-sitter.

چانک‌ها در سطح کلاس یا متد کامل ساخته می‌شوند (نه تعداد خط ثابت).
javadoc و امضای کلاس دربرگیرنده به‌عنوان context همراه هر چانک ذخیره می‌شود.
این ماژول فقط می‌خواند؛ هیچ فایلی را تغییر نمی‌دهد.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import tree_sitter
import tree_sitter_java

TYPE_DECLARATIONS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

MEMBER_DECLARATIONS = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "compact_constructor_declaration": "constructor",
}

BODY_NODE_TYPES = {
    "class_body",
    "interface_body",
    "enum_body",
    "record_declaration_body",
    "annotation_type_body",
}


@dataclass(frozen=True)
class CodeChunk:
    """یک چانک قابل ایندکس: متن برای embedding + متادیتا برای ارجاع به منبع."""

    chunk_id: str
    embed_text: str          # متن نهایی که embed می‌شود (context + کد)
    file_path: str           # مسیر نسبی فایل در کدبیس
    start_line: int          # 1-based
    end_line: int            # 1-based
    package: str
    class_name: str          # نام کامل کلاس دربرگیرنده (مثل Outer.Inner)
    method_name: str         # خالی برای چانک‌های سطح کلاس
    chunk_type: str          # class | interface | enum | record | annotation | method | constructor
    class_signature: str
    javadoc: str


_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())


class JavaChunker:
    """فایل جاوا را parse و به چانک‌های سطح کلاس/متد تبدیل می‌کند."""

    def __init__(self, max_chunk_chars: int = 6000):
        self._parser = tree_sitter.Parser(_LANGUAGE)
        self._max_chunk_chars = max_chunk_chars

    def chunk_file(self, source: bytes, file_path: str) -> list[CodeChunk]:
        tree = self._parser.parse(source)
        root = tree.root_node
        package = self._find_package(root, source)
        chunks: list[CodeChunk] = []
        for node in root.named_children:
            if node.type in TYPE_DECLARATIONS:
                self._walk_type(node, source, file_path, package, parents=[], out=chunks)
        return chunks

    # ---------- پیمایش ----------

    def _walk_type(
        self,
        type_node: tree_sitter.Node,
        source: bytes,
        file_path: str,
        package: str,
        parents: list[str],
        out: list[CodeChunk],
    ) -> None:
        kind = TYPE_DECLARATIONS[type_node.type]
        name = self._child_identifier(type_node)
        qualified_name = ".".join(parents + [name]) if name else ".".join(parents) or "?"
        signature = self._declaration_signature(type_node, source)
        javadoc = self._preceding_javadoc(type_node, source)

        body = next((c for c in type_node.children if c.type in BODY_NODE_TYPES), None)
        members = list(body.named_children) if body is not None else []

        out.append(
            self._make_class_chunk(
                type_node, source, file_path, package, qualified_name,
                kind, signature, javadoc, members,
            )
        )

        for member in members:
            if member.type in MEMBER_DECLARATIONS:
                out.append(
                    self._make_method_chunk(
                        member, source, file_path, package, qualified_name,
                        MEMBER_DECLARATIONS[member.type], signature,
                    )
                )
            elif member.type in TYPE_DECLARATIONS:
                self._walk_type(member, source, file_path, package,
                                parents + [name] if name else parents, out)

    # ---------- ساخت چانک ----------

    def _make_class_chunk(
        self,
        node: tree_sitter.Node,
        source: bytes,
        file_path: str,
        package: str,
        qualified_name: str,
        kind: str,
        signature: str,
        javadoc: str,
        members: list[tree_sitter.Node],
    ) -> CodeChunk:
        # اسکلت کلاس: امضا + فیلدها + امضای متدها (بدون بدنه) تا چانک کلاس کوچک بماند
        skeleton_lines = [signature + " {"]
        for member in members:
            text = self._text(member, source)
            if member.type in ("field_declaration", "constant_declaration", "enum_constant"):
                skeleton_lines.append("    " + text)
            elif member.type in MEMBER_DECLARATIONS:
                skeleton_lines.append("    " + self._declaration_signature(member, source) + ";")
            elif member.type in TYPE_DECLARATIONS:
                skeleton_lines.append(
                    "    " + self._declaration_signature(member, source) + " { ... }"
                )
        skeleton_lines.append("}")
        skeleton = "\n".join(skeleton_lines)

        start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
        header = self._context_header(file_path, start_line, end_line, package)
        body_text = (javadoc + "\n" if javadoc else "") + skeleton
        return CodeChunk(
            chunk_id=self._chunk_id(file_path, start_line, qualified_name, ""),
            embed_text=self._truncate(header + body_text),
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            package=package,
            class_name=qualified_name,
            method_name="",
            chunk_type=kind,
            class_signature=signature,
            javadoc=javadoc,
        )

    def _make_method_chunk(
        self,
        node: tree_sitter.Node,
        source: bytes,
        file_path: str,
        package: str,
        class_name: str,
        kind: str,
        class_signature: str,
    ) -> CodeChunk:
        method_name = self._child_identifier(node)
        javadoc = self._preceding_javadoc(node, source)
        start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
        header = self._context_header(
            file_path, start_line, end_line, package, class_signature
        )
        body_text = (javadoc + "\n" if javadoc else "") + self._text(node, source)
        return CodeChunk(
            chunk_id=self._chunk_id(file_path, start_line, class_name, method_name),
            embed_text=self._truncate(header + body_text),
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            package=package,
            class_name=class_name,
            method_name=method_name,
            chunk_type=kind,
            class_signature=class_signature,
            javadoc=javadoc,
        )

    # ---------- کمکی‌ها ----------

    @staticmethod
    def _text(node: tree_sitter.Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _find_package(self, root: tree_sitter.Node, source: bytes) -> str:
        for child in root.named_children:
            if child.type == "package_declaration":
                for sub in child.named_children:
                    if sub.type in ("scoped_identifier", "identifier"):
                        return self._text(sub, source)
        return ""

    def _child_identifier(self, node: tree_sitter.Node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return self._text_from_node(name_node, node)
        for child in node.named_children:
            if child.type == "identifier":
                return child.text.decode("utf-8", errors="replace")
        return ""

    @staticmethod
    def _text_from_node(node: tree_sitter.Node, _parent: tree_sitter.Node) -> str:
        return node.text.decode("utf-8", errors="replace")

    def _declaration_signature(self, node: tree_sitter.Node, source: bytes) -> str:
        """متن اعلان از ابتدای node تا شروع بدنه — شامل annotationها و extends/implements."""
        end_byte = node.end_byte
        for child in node.children:
            if child.type in BODY_NODE_TYPES or child.type == "block":
                end_byte = child.start_byte
                break
        signature = source[node.start_byte : end_byte].decode("utf-8", errors="replace")
        return " ".join(signature.split())

    def _preceding_javadoc(self, node: tree_sitter.Node, source: bytes) -> str:
        prev = node.prev_sibling
        while prev is not None and prev.type == "line_comment":
            prev = prev.prev_sibling
        if prev is not None and prev.type == "block_comment":
            text = self._text(prev, source)
            if text.startswith("/**"):
                return text
        return ""

    @staticmethod
    def _context_header(
        file_path: str,
        start_line: int,
        end_line: int,
        package: str,
        class_signature: str = "",
    ) -> str:
        lines = [f"// File: {file_path} (lines {start_line}-{end_line})"]
        if package:
            lines.append(f"// Package: {package}")
        if class_signature:
            lines.append(f"// Enclosing type: {class_signature}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _chunk_id(file_path: str, start_line: int, class_name: str, method_name: str) -> str:
        key = f"{file_path}:{start_line}:{class_name}:{method_name}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def _truncate(self, text: str) -> str:
        if len(text) <= self._max_chunk_chars:
            return text
        return text[: self._max_chunk_chars] + "\n// ... (truncated)"
