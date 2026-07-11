"""پرامپت‌های سیستم و قالب‌های پرسش.

دو حالت زبانی دارد: پاسخ‌های تعاملی ترمینال انگلیسی هستند و خروجی‌های
فایل (docgen و save) فارسی. سوال کاربر به هر دو زبان پذیرفته می‌شود.
"""

SYSTEM_RULES = """You are a documentation and code-analysis assistant for a Java codebase (Spring Boot / Spring Batch). You only have access to the retrieved code chunks included in this message.

Non-negotiable rules:

1. Always cite the source of every claim with the file path and line range (e.g. src/main/java/com/example/FooService.java lines 12-40). If the retrieved chunks are not sufficient to answer, say explicitly that the information is not available in the retrieved chunks — never guess the behavior of the code.

2. Never suggest code changes and never write new code; your output is only explanation, analysis, or documentation.

3. For batch logic (side-effects, transactions, error handling), separate exactly what you *observed* in the code from what you *inferred*. Present these under two separate headings."""

LANG_RULE_EN = """
4. Answer in clear, simple English, regardless of the language of the user's question (it may be Persian or English). Class names, method names, and file paths stay untouched. Use "Observed in the code" and "Inferred" as the two headings from rule 3."""

LANG_RULE_FA = """
4. زبان خروجی همیشه فارسی است — ساده، مستقیم و بدون اصطلاحات ترجمه‌ی نامفهوم. اصطلاحات فنی رایج مثل transaction، batch، thread همان‌طور لاتین بمانند. نام کلاس‌ها، متدها و مسیر فایل‌ها دست‌نخورده و انگلیسی بمانند. عنوان دو بخش قاعده‌ی ۳ را «مشاهده‌شده از کد» و «استنباط» بگذار.

5. همیشه به فارسی روان و ساده پاسخ بده، حتی اگر چانک‌های بازیابی‌شده (کد و کامنت‌ها) انگلیسی هستند."""


def system_prompt(lang: str) -> str:
    """lang: «en» برای پاسخ ترمینال، «fa» برای خروجی فایل/مستند."""
    return SYSTEM_RULES + (LANG_RULE_FA if lang == "fa" else LANG_RULE_EN)


ASK_USER_TEMPLATE = """Retrieved code chunks from the codebase index (each with its file path and line range):

{context}

---

User question: {question}

Answer only based on the chunks above, and cite the file path and line range for every claim."""


DOCGEN_USER_TEMPLATE = """Retrieved code chunks for "{target}" (each with its file path and line range):

{context}

---

برای «{target}» یک مستند Markdown فارسی تولید کن با این بخش‌ها:

## مسئولیت
نقش و مسئولیت اصلی (فقط بر اساس کد مشاهده‌شده).

## ورودی/خروجی
متدهای اصلی، پارامترها و مقدار بازگشتی آن‌ها.

## وابستگی‌ها
کلاس‌ها و کامپوننت‌هایی که به آن‌ها وابسته است (فیلدها، پارامترهای constructor، importهای قابل مشاهده در چانک‌ها).

برای هر بخش، منبع (مسیر فایل و بازه‌ی خط) را ذکر کن. اگر برای بخشی اطلاعات کافی در چانک‌ها نیست، همان را صریح بنویس."""


def format_context(chunks) -> str:
    """چانک‌های بازیابی‌شده را به متن context برای پرامپت تبدیل می‌کند."""
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        blocks.append(
            f"### Chunk {i} — {meta.get('file_path')} "
            f"(lines {meta.get('start_line')}-{meta.get('end_line')})\n"
            f"```java\n{chunk.document}\n```"
        )
    return "\n\n".join(blocks)
