"""تست تبدیل نمایش RTL برای ترمینال."""

from java_doc_assistant.display import to_terminal


def test_rtl_fix_disabled_keeps_logical_order(monkeypatch):
    """وقتی خروجی ترمینال نیست (pipe/فایل) متن باید دست‌نخورده بماند."""
    monkeypatch.setenv("CASPRAG_RTL_FIX", "0")
    text = "ایندکس آماده است (28 چانک)."
    assert to_terminal(text) == text


def test_rtl_fix_enabled_reorders_persian(monkeypatch):
    monkeypatch.setenv("CASPRAG_RTL_FIX", "1")
    text = "ایندکس آماده است"
    fixed = to_terminal(text)
    assert fixed != text
    # حروف باید به شکل چسبیده (presentation forms) تبدیل شده باشند
    assert any("ﭐ" <= ch <= "﷿" or "ﹰ" <= ch <= "﻿" for ch in fixed)


def test_rtl_fix_preserves_latin_and_digits(monkeypatch):
    monkeypatch.setenv("CASPRAG_RTL_FIX", "1")
    fixed = to_terminal("تعداد کلاس‌ها: 8 در پکیج com.example.bank")
    assert "com.example.bank" in fixed
    assert "8" in fixed


def test_latin_only_lines_untouched(monkeypatch):
    monkeypatch.setenv("CASPRAG_RTL_FIX", "1")
    banner_line = r" \____\__,_|___/ .__/  |_| \_\/_/   \_\____|"
    assert to_terminal(banner_line) == banner_line


def test_multiline_mixed(monkeypatch):
    monkeypatch.setenv("CASPRAG_RTL_FIX", "1")
    text = "خط فارسی\nsrc/main/App.java\nخط دوم"
    lines = to_terminal(text).split("\n")
    assert lines[1] == "src/main/App.java"  # خط لاتین دست‌نخورده
    assert lines[0] != "خط فارسی"           # خط فارسی تبدیل‌شده
