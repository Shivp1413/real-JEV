"""Persistent app settings (active model, backend, web-search API keys).

Stored as JSON next to the project. API keys live here so the app can use them for
web search; the file is git-ignored so you never commit your keys.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .catalog import DEFAULT_MODEL

CONFIG_DIR = Path(os.environ.get("REALJEV_CONFIG_DIR", Path.home() / ".real-jev"))
CONFIG_FILE = CONFIG_DIR / "settings.json"

_lock = threading.Lock()

DEFAULTS = {
    # LLM backend: "ollama" (default) or "openai" (any OpenAI-compatible server:
    # vLLM, llama.cpp server, LM Studio, etc.)
    "backend": os.environ.get("REALJEV_BACKEND", "ollama"),
    "ollama_url": os.environ.get("REALJEV_OLLAMA_URL", "http://127.0.0.1:11434"),
    "openai_base_url": os.environ.get("REALJEV_OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"),
    "openai_api_key": os.environ.get("REALJEV_OPENAI_API_KEY", ""),
    "model": os.environ.get("REALJEV_MODEL", DEFAULT_MODEL),
    "temperature": 0.0,
    # Web search
    "web_search_enabled": False,
    "web_search_provider": "brave",  # "brave" or "firecrawl"
    "brave_api_key": os.environ.get("BRAVE_API_KEY", ""),
    "firecrawl_api_key": os.environ.get("FIRECRAWL_API_KEY", ""),
    "web_search_results": 4,
}

_settings = None


def _load():
    global _settings
    data = dict(DEFAULTS)
    try:
        if CONFIG_FILE.exists():
            data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    _settings = data
    return data


def get_all():
    with _lock:
        if _settings is None:
            _load()
        return dict(_settings)


def get(key, default=None):
    return get_all().get(key, default)


def update(patch: dict):
    with _lock:
        if _settings is None:
            _load()
        for k, v in patch.items():
            if k in DEFAULTS:  # only allow known keys
                _settings[k] = v
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(_settings, indent=2), encoding="utf-8")
        return dict(_settings)


def public_view():
    """Settings safe to send to the browser (API keys masked)."""
    s = get_all()
    out = dict(s)
    for k in ("brave_api_key", "firecrawl_api_key", "openai_api_key"):
        v = s.get(k) or ""
        out[k + "_set"] = bool(v)
        out[k] = (v[:3] + "\u2022\u2022\u2022\u2022" + v[-2:]) if len(v) > 6 else ("\u2022\u2022\u2022\u2022" if v else "")
    return out
