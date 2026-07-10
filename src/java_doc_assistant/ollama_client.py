"""کلاینت سرور داخلی سازگار با Ollama — embedding و chat.

اینترفیس‌های EmbeddingClient و ChatClient جدا تعریف شده‌اند تا بعداً بتوان
backend را بدون تغییر منطق اصلی عوض کرد.
تنها مقصد شبکه‌ای این ماژول base_url پیکربندی‌شده است.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import requests


class LLMServerError(Exception):
    pass


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatClient(ABC):
    @abstractmethod
    def chat(self, system: str, user: str) -> str: ...


class OllamaEmbeddingClient(EmbeddingClient):
    """embedding از طریق /api/embed (و fallback به /api/embeddings قدیمی)."""

    def __init__(self, base_url: str, model: str, timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self._base_url}/api/embed"
        try:
            resp = self._session.post(
                url,
                json={"model": self._model, "input": texts},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise LLMServerError(
                f"اتصال به سرور embedding ({url}) برقرار نشد: {exc}"
            ) from exc
        if resp.status_code == 404:
            return self._embed_legacy(texts)
        if resp.status_code != 200:
            raise LLMServerError(
                f"خطای سرور embedding ({resp.status_code}): {resp.text[:500]}"
            )
        data = resp.json()
        embeddings = data.get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
            raise LLMServerError("پاسخ سرور embedding ناقص است (کلید 'embeddings').")
        return embeddings

    def _embed_legacy(self, texts: list[str]) -> list[list[float]]:
        """سرورهای قدیمی‌تر Ollama فقط /api/embeddings تکی دارند."""
        url = f"{self._base_url}/api/embeddings"
        out: list[list[float]] = []
        for text in texts:
            resp = self._session.post(
                url,
                json={"model": self._model, "prompt": text},
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                raise LLMServerError(
                    f"خطای سرور embedding ({resp.status_code}): {resp.text[:500]}"
                )
            out.append(resp.json()["embedding"])
        return out


class OllamaChatClient(ChatClient):
    """تولید پاسخ از طریق /api/chat (بدون streaming)."""

    def __init__(self, base_url: str, model: str, timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = requests.Session()

    def chat(self, system: str, user: str) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        try:
            resp = self._session.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise LLMServerError(f"اتصال به سرور مدل ({url}) برقرار نشد: {exc}") from exc
        if resp.status_code != 200:
            raise LLMServerError(
                f"خطای سرور مدل ({resp.status_code}): {resp.text[:500]}"
            )
        data = resp.json()
        message = (data.get("message") or {}).get("content")
        if message is None:
            raise LLMServerError("پاسخ سرور مدل ناقص است (کلید 'message.content').")
        return message
