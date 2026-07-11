"""بارگذاری و اعتبارسنجی پیکربندی از config.yaml.

هیچ مقدار مربوط به سرور یا نام مدل در کد هاردکد نمی‌شود؛ همه از این فایل می‌آید.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    base_url: str
    timeout_seconds: int
    chat_model: str
    embedding_model: str
    chroma_path: str
    chroma_collection: str
    top_k: int
    max_chunk_chars: int
    docs_dir: str


DEFAULT_CONFIG_ENV = "JAVA_DOC_ASSISTANT_CONFIG"


def find_config_path(explicit: str | None = None) -> Path:
    """مسیر فایل پیکربندی: آرگومان صریح > متغیر محیطی > ./config.yaml"""
    if explicit:
        return Path(explicit)
    env = os.environ.get(DEFAULT_CONFIG_ENV)
    if env:
        return Path(env)
    return Path("config.yaml")


def load_config(path: str | None = None) -> Config:
    cfg_path = find_config_path(path)
    if not cfg_path.is_file():
        raise ConfigError(
            f"Config file not found: {cfg_path}\n"
            f"Create a config.yaml or point to one with --config or the "
            f"{DEFAULT_CONFIG_ENV} environment variable."
        )
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    def section(name: str) -> dict:
        value = raw.get(name) or {}
        if not isinstance(value, dict):
            raise ConfigError(f"Section '{name}' in config.yaml must be a mapping.")
        return value

    server = section("server")
    models = section("models")
    chroma = section("chroma")
    retrieval = section("retrieval")
    index = section("index")
    output = section("output")

    base_url = str(server.get("base_url", "")).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigError(
            "server.base_url must be a valid http/https URL (the internal Ollama-compatible server)."
        )
    chat_model = str(models.get("chat", "")).strip()
    embedding_model = str(models.get("embedding", "")).strip()
    if not chat_model or not embedding_model:
        raise ConfigError("models.chat and models.embedding must both be set in config.yaml.")

    return Config(
        base_url=base_url,
        timeout_seconds=int(server.get("timeout_seconds", 300)),
        chat_model=chat_model,
        embedding_model=embedding_model,
        chroma_path=str(chroma.get("path", "./.java-doc-index")),
        chroma_collection=str(chroma.get("collection", "java_code")),
        top_k=int(retrieval.get("top_k", 8)),
        max_chunk_chars=int(index.get("max_chunk_chars", 6000)),
        docs_dir=str(output.get("docs_dir", "./generated-docs")),
    )
