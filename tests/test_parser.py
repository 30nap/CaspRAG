from pathlib import Path

from java_doc_assistant.parser import JavaChunker

SAMPLE = Path(__file__).resolve().parent.parent / "sample_project"


def _chunks_for(rel: str):
    path = SAMPLE / "src/main/java" / rel
    return JavaChunker().chunk_file(path.read_bytes(), rel)


def test_class_and_method_chunks():
    chunks = _chunks_for("com/example/bank/service/AccountService.java")
    by_type = {}
    for c in chunks:
        by_type.setdefault(c.chunk_type, []).append(c)

    assert len(by_type["class"]) == 1
    cls = by_type["class"][0]
    assert cls.class_name == "AccountService"
    assert cls.package == "com.example.bank.service"
    assert "extends BaseService implements AccountOperations" in cls.class_signature
    assert cls.javadoc.startswith("/**")

    methods = {c.method_name for c in by_type["method"]}
    assert {"register", "requireAccount", "transfer"} <= methods

    transfer = next(c for c in by_type["method"] if c.method_name == "transfer")
    # امضای کلاس والد باید در context چانک متد باشد
    assert "extends BaseService" in transfer.embed_text
    # javadoc متد باید همراه چانک باشد
    assert "Debits the source first" in transfer.embed_text
    assert transfer.start_line > 1 and transfer.end_line >= transfer.start_line


def test_nested_enum_and_record():
    chunks = _chunks_for("com/example/bank/model/Account.java")
    names = {(c.chunk_type, c.class_name) for c in chunks if c.chunk_type != "method"}
    assert ("class", "Account") in names
    assert ("enum", "Account.Status") in names

    rec = _chunks_for("com/example/bank/model/TransferRecord.java")
    assert any(c.chunk_type == "record" and c.class_name == "TransferRecord" for c in rec)
    assert any(c.method_name == "isWellFormed" for c in rec)


def test_interface():
    chunks = _chunks_for("com/example/bank/service/AccountOperations.java")
    iface = next(c for c in chunks if c.chunk_type == "interface")
    assert iface.class_name == "AccountOperations"
    assert any(c.method_name == "transfer" for c in chunks)
