"""تست انتها-به-انتها: index و ask و docgen روی sample_project با سرور آزمایشی Ollama.

قرارداد زبانی: خروجی ترمینال انگلیسی است؛ فایل‌های تولیدی (docgen و save) فارسی.
سرور آزمایشی زبان خواسته‌شده را در پاسخ تگ می‌کند (lang=en / lang=fa).
"""

import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from java_doc_assistant.cli import main
from tests.mock_ollama import start_server

SAMPLE = Path(__file__).resolve().parent.parent / "sample_project"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    server, base_url = start_server()
    root = tmp_path_factory.mktemp("env")
    config = {
        "server": {"base_url": base_url, "timeout_seconds": 30},
        "models": {"chat": "mock-chat", "embedding": "mock-embed"},
        "chroma": {"path": str(root / "index"), "collection": "java_code"},
        "retrieval": {"top_k": 5},
        "index": {"max_chunk_chars": 6000},
        "output": {"docs_dir": str(root / "docs")},
    }
    cfg_path = root / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["index", str(SAMPLE), "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    yield {"runner": runner, "cfg": str(cfg_path), "root": root, "index_output": result.output}
    server.shutdown()


def test_index_reports_all_files(env):
    out = env["index_output"]
    assert "7 files" in out
    assert "AccountService.java" in out


def test_ask_prints_english_answer_with_sources(env):
    """سوال فارسی → پاسخ ترمینال انگلیسی با ارجاع فایل/خط؛ بدون ساخت فایل."""
    result = env["runner"].invoke(
        main, ["ask", "متد transfer در AccountService چیکار می‌کنه؟", "--config", env["cfg"]]
    )
    assert result.exit_code == 0, result.output
    assert "[mock answer lang=en]" in result.output
    assert "--- Sources ---" in result.output
    assert re.search(r"\.java \(lines \d+-\d+\)", result.output)
    assert not (env["root"] / "docs").exists()


def test_ask_accepts_english_questions(env):
    result = env["runner"].invoke(
        main, ["ask", "What does the transfer method do?", "--config", env["cfg"]]
    )
    assert result.exit_code == 0, result.output
    assert "[mock answer lang=en]" in result.output


def test_ask_statistical_answers_without_llm(env):
    runner, cfg = env["runner"], env["cfg"]

    # فارسی
    result = runner.invoke(main, ["ask", "کل تعداد کلاس‌های پروژه چقدره؟", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "computed directly from the index" in result.output
    # Account, Status(enum), TransferRecord, AccountOperations, BaseService,
    # AccountService, TransferItemProcessor, TransferJobConfig = 8
    assert "8" in result.output

    # انگلیسی
    result = runner.invoke(main, ["ask", "how many classes are there?", "--config", cfg])
    assert "computed directly from the index" in result.output
    assert "8" in result.output

    result = runner.invoke(main, ["ask", "لیست پکیج‌ها رو بده", "--config", cfg])
    assert result.exit_code == 0
    assert "com.example.bank.batch" in result.output
    assert "com.example.bank.service" in result.output

    result = runner.invoke(main, ["ask", "تعداد فایل ها چندتاست", "--config", cfg])
    assert "7" in result.output


def test_ask_save_writes_persian_markdown(env):
    out_file = env["root"] / "docs" / "answer.md"
    result = env["runner"].invoke(
        main,
        ["ask", "منطق batch چطور کار می‌کند؟", "--save", "--out", str(out_file),
         "--config", env["cfg"]],
    )
    assert result.exit_code == 0, result.output
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "[mock answer lang=fa]" in content  # فایل ذخیره‌شده فارسی است
    assert "## منابع بازیابی‌شده" in content


def test_docgen_package_writes_persian_markdown(env):
    result = env["runner"].invoke(
        main, ["docgen", "--package", "com.example.bank.batch", "--config", env["cfg"]]
    )
    assert result.exit_code == 0, result.output
    doc = env["root"] / "docs" / "doc-com_example_bank_batch.md"
    assert doc.is_file()
    assert "[mock answer lang=fa]" in doc.read_text(encoding="utf-8")


def test_docgen_class_by_simple_name(env):
    out_file = env["root"] / "docs" / "account-service.md"
    result = env["runner"].invoke(
        main,
        ["docgen", "--class", "AccountService", "-o", str(out_file), "--config", env["cfg"]],
    )
    assert result.exit_code == 0, result.output
    assert out_file.is_file()


def test_docgen_requires_exactly_one_target(env):
    result = env["runner"].invoke(main, ["docgen", "--config", env["cfg"]])
    assert result.exit_code != 0


def test_interactive_repl(env):
    """اجرای بدون زیر‌دستور باید REPL را باز کند: سوال آزاد + دستورهای اسلشی."""
    repl_input = "\n".join([
        "کل تعداد کلاس‌های پروژه چقدره؟",   # آماری، بدون LLM
        "متد transfer چیکار می‌کنه؟",        # RAG → پاسخ انگلیسی در ترمینال
        "/docgen com.example.bank.model",
        "/save " + str(env["root"] / "docs" / "repl-answer.md"),
        "/help",
        "/exit",
    ]) + "\n"
    result = env["runner"].invoke(main, ["--config", env["cfg"]], input=repl_input)
    assert result.exit_code == 0, result.output
    assert "casprag>" in result.output
    assert "computed directly from the index" in result.output
    assert "[mock answer lang=en]" in result.output
    assert "/index" in result.output  # خروجی /help
    assert (env["root"] / "docs" / "doc-com_example_bank_model.md").is_file()
    saved = env["root"] / "docs" / "repl-answer.md"
    assert saved.is_file()
    # فایل /save باید فارسی باشد حتی وقتی پاسخ ترمینال انگلیسی بوده
    assert "[mock answer lang=fa]" in saved.read_text(encoding="utf-8")


def test_repl_unknown_command_and_empty_docgen(env):
    repl_input = "/foo\n/docgen not.a.real.package\n/exit\n"
    result = env["runner"].invoke(main, ["--config", env["cfg"]], input=repl_input)
    assert result.exit_code == 0, result.output
    assert "Unknown command" in result.output
    assert "No chunks found" in result.output


def test_codebase_untouched(env):
    """ابزار فقط-خواندنی است: هیچ فایلی داخل sample_project نباید تغییر کند یا اضافه شود."""
    java_files = sorted(p.name for p in SAMPLE.rglob("*") if p.is_file())
    assert java_files == [
        "Account.java", "AccountOperations.java", "AccountService.java",
        "BaseService.java", "TransferItemProcessor.java", "TransferJobConfig.java",
        "TransferRecord.java",
    ]
