"""نقطه‌ی ورود باینری PyInstaller برای casprag."""

import multiprocessing

from java_doc_assistant.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # لازم برای exe ویندوز
    main()
