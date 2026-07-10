"""سرور آزمایشی سازگار با Ollama برای تست لوکال — بدون هیچ مدل واقعی.

embedding قطعی (bag-of-words هش‌شده) برمی‌گرداند تا بازیابی معنادار باشد،
و /api/chat یک پاسخ فارسی ساختگی می‌دهد که چانک‌های دریافتی را بازتاب می‌دهد.
فقط برای تست پایپ‌لاین است؛ کیفیت پاسخ مدل واقعی را شبیه‌سازی نمی‌کند.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 256


def fake_embedding(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in re.findall(r"[A-Za-z_؀-ۿ][\w؀-ۿ]*", text.lower()):
        h = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big")
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/embed":
            body = {"embeddings": [fake_embedding(t) for t in payload.get("input", [])]}
        elif self.path == "/api/embeddings":
            body = {"embedding": fake_embedding(payload.get("prompt", ""))}
        elif self.path == "/api/chat":
            user = next(
                (m["content"] for m in payload.get("messages", []) if m["role"] == "user"),
                "",
            )
            refs = re.findall(r"([\w/.-]+\.java) \(خطوط (\d+)-(\d+)\)", user)
            cited = "؛ ".join(f"{f} خطوط {a}-{b}" for f, a, b in refs[:3]) or "منبعی یافت نشد"
            body = {
                "message": {
                    "role": "assistant",
                    "content": f"[پاسخ آزمایشی به فارسی] بر اساس چانک‌های بازیابی‌شده: {cited}",
                },
                "done": True,
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # ساکت
        pass


def start_server(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    srv, url = start_server(11434)
    print(f"mock ollama at {url} — Ctrl+C برای توقف")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
