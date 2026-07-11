"""نمایش درست متن فارسی (RTL) در ترمینال.

بیشتر ترمینال‌ها (مخصوصاً cmd/PowerShell ویندوز) الگوریتم bidi را اجرا نمی‌کنند
و متن فارسی را برعکس نشان می‌دهند. این ماژول قبل از چاپ، متن را با
arabic-reshaper (چسباندن حروف) و python-bidi (ترتیب دیداری) تبدیل می‌کند.

فقط خروجی ترمینال تبدیل می‌شود؛ فایل‌های Markdown با ترتیب منطقی (استاندارد)
ذخیره می‌شوند تا در ویرایشگرها و مرورگرها درست باشند. وقتی خروجی pipe یا
redirect شده باشد هم تبدیل انجام نمی‌شود تا متن ماشین‌خوان بماند.

کنترل دستی با متغیر محیطی CASPRAG_RTL_FIX: مقدار 1 اجبار به تبدیل، 0 خاموش.
"""

from __future__ import annotations

import os
import re
import sys

import arabic_reshaper
import click

try:  # python-bidi >= 0.6
    from bidi import get_display
except ImportError:  # نسخه‌های قدیمی‌تر
    from bidi.algorithm import get_display

_RTL_CHARS = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

_reshaper = arabic_reshaper.ArabicReshaper()


def _fix_enabled(err: bool = False) -> bool:
    forced = os.environ.get("CASPRAG_RTL_FIX")
    if forced == "1":
        return True
    if forced == "0":
        return False
    stream = sys.stderr if err else sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


def to_terminal(text: str, err: bool = False) -> str:
    """متن را در صورت نیاز برای نمایش در ترمینال LTR آماده می‌کند (خط به خط)."""
    if not text or not _fix_enabled(err) or not _RTL_CHARS.search(text):
        return text
    lines = []
    for line in text.split("\n"):
        if _RTL_CHARS.search(line):
            lines.append(get_display(_reshaper.reshape(line)))
        else:
            lines.append(line)
    return "\n".join(lines)


def echo(message: str = "", err: bool = False) -> None:
    """جایگزین click.echo برای همه‌ی خروجی‌های ترمینال ابزار."""
    click.echo(to_terminal(message, err=err), err=err)


def prompt_text(text: str) -> str:
    """متن prompt ورودی (مثل «casprag> ») — همان تبدیل نمایش."""
    return to_terminal(text)
