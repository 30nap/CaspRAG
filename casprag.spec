# -*- mode: python ; coding: utf-8 -*-
# ساخت باینری تک‌فایلی casprag با PyInstaller:
#   pyinstaller casprag.spec
# خروجی: dist/casprag.exe (ویندوز) یا dist/casprag (لینوکس/مک)

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# chromadb فایل‌های داده (migrations و ...) و کتابخانه‌ی native دارد؛
# tree-sitter-java هم extension کامپایل‌شده دارد — همه باید داخل باینری بیایند
for pkg in ("chromadb", "tree_sitter", "tree_sitter_java"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# chromadb در runtime نسخه‌ی خودش را از متادیتای پکیج می‌خواند
for pkg in ("chromadb", "opentelemetry-api", "opentelemetry-sdk"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

a = Analysis(
    ["packaging/pyinstaller_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # این‌ها فقط برای embedding function پیش‌فرض Chroma لازم‌اند که casprag
    # استفاده نمی‌کند (embedding از سرور Ollama می‌آید) — حذف‌شان حجم exe را
    # به‌شدت کم می‌کند
    excludes=[
        "onnxruntime",
        "tokenizers",
        "huggingface_hub",
        "kubernetes",
        "pytest",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="casprag",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
