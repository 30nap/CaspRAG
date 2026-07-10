# java-doc-assistant

دستیار **فقط-خواندنی** پرسش‌وپاسخ و مستندسازی برای کدبیس‌های جاوا (Spring Boot / Spring Batch) با RAG کاملاً لوکال.

- چانک‌سازی ساختاری با `tree-sitter-java` در سطح **کلاس/متد کامل** (javadoc و امضای کلاس دربرگیرنده به‌عنوان context همراه هر چانک ذخیره می‌شود)
- ذخیره‌سازی برداری در **Chroma** (لوکال و persistent)
- embedding و تولید پاسخ از طریق سرور داخلی سازگار با **Ollama** (`/api/embed` و `/api/chat`) — آدرس سرور و نام هر دو مدل فقط در `config.yaml` تنظیم می‌شود
- پاسخ‌ها همیشه **فارسی** و همیشه با ارجاع صریح به مسیر فایل و بازه‌ی خط

## محدودیت‌های امنیتی (طراحی‌شده برای کد بانکی)

- ابزار کدبیس را **فقط می‌خواند**؛ هیچ قابلیت نوشتن/ویرایش فایل کدبیس، apply_diff یا اجرای shell ندارد.
- تنها محل‌های نوشتن: دایرکتوری ایندکس Chroma (`chroma.path`) و فایل‌های Markdown خروجی (`output.docs_dir`).
- تنها مقصد شبکه‌ای، `server.base_url` در config است؛ telemetry مربوط به Chroma هم خاموش شده است.

## نصب

```bash
python3 -m pip install .
```

(نیازمند Python 3.11+)

## پیکربندی

فایل `config.yaml` (نمونه در ریشه‌ی ریپازیتوری) را ویرایش کنید:

```yaml
server:
  base_url: "http://your-internal-server:11434"
models:
  chat: "qwen2.5-coder:32b"       # مدل تولید پاسخ
  embedding: "nomic-embed-text"   # مدل embedding (جدا از مدل تولید)
chroma:
  path: "./.java-doc-index"
```

مسیر config با اولویت: `--config` > متغیر محیطی `JAVA_DOC_ASSISTANT_CONFIG` > `./config.yaml`.

## استفاده

```bash
# ۱) ایندکس کردن یک ریپازیتوری جاوا
java-doc-assistant index /path/to/java/project

# ۲) پرسش — خروجی پیش‌فرض چاپ در ترمینال است، فایلی ساخته نمی‌شود
java-doc-assistant ask "متد transfer در AccountService چیکار می‌کنه؟"

# سوالات آماری ساده بدون فراخوانی مدل، مستقیم از ایندکس جواب می‌گیرند
java-doc-assistant ask "تعداد کلاس‌های پروژه چقدره؟"
java-doc-assistant ask "لیست پکیج‌ها"

# ذخیره‌ی پاسخ به‌صورت فایل Markdown فقط با پرچم صریح --save
java-doc-assistant ask "منطق batch را توضیح بده" --save --out report.md

# ۳) تولید مستند Markdown برای یک پکیج یا کلاس (همیشه فایل می‌سازد)
java-doc-assistant docgen --package com.example.bank.batch
java-doc-assistant docgen --class AccountService -o docs/account-service.md
```

## تست

تست‌ها با یک سرور آزمایشی سازگار با Ollama (بدون مدل واقعی) روی پروژه‌ی نمونه‌ی `sample_project/` اجرا می‌شوند:

```bash
python3 -m pip install pytest
python3 -m pytest tests/ -v
```

برای آزمایش دستی بدون سرور واقعی: `python3 tests/mock_ollama.py` یک سرور آزمایشی روی پورت 11434 بالا می‌آورد.

## ساختار کد

```
src/java_doc_assistant/
  cli.py            دستورهای index / ask / docgen
  config.py         بارگذاری config.yaml (هیچ آدرس/مدلی هاردکد نیست)
  parser.py         چانک‌سازی tree-sitter (کلاس/متد + javadoc + امضای کلاس)
  indexer.py        پیمایش .java → چانک → embedding → Chroma
  store.py          اینترفیس VectorStore + پیاده‌سازی Chroma (قابل تعویض)
  ollama_client.py  اینترفیس‌های EmbeddingClient/ChatClient + پیاده‌سازی Ollama (قابل تعویض)
  rag.py            بازیابی و ساخت پرامپت برای ask / docgen
  stats.py          پاسخ آماری rule-based بدون LLM
  prompts.py        system prompt فارسی و قالب‌های پرسش
```

لایه‌های vector store و کلاینت مدل پشت اینترفیس (ABC) هستند؛ تعویض Chroma یا backend مدل نیازی به تغییر منطق اصلی (`rag.py`, `indexer.py`, `cli.py`) ندارد.
