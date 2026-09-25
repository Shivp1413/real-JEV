"""LLM backends for real-JEV.

Primary backend is Ollama (native /api endpoints, so we can force JSON output and
stream model pulls). A generic OpenAI-compatible backend is also supported for
vLLM / llama.cpp server / LM Studio. If neither is reachable, a deterministic mock
backend keeps the UI fully usable (clearly labelled as demo mode).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterator, Optional

import requests

from . import settings


class BackendError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #
def _ollama_url() -> str:
    return settings.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")


def ollama_available(timeout: float = 1.5) -> bool:
    try:
        r = requests.get(_ollama_url() + "/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ollama_list_models() -> list[dict]:
    r = requests.get(_ollama_url() + "/api/tags", timeout=5)
    r.raise_for_status()
    data = r.json()
    out = []
    for m in data.get("models", []):
        out.append(
            {
                "tag": m.get("name"),
                "size_bytes": m.get("size"),
                "modified": m.get("modified_at"),
            }
        )
    return out


def ollama_pull_stream(tag: str) -> Iterator[dict]:
    """Yield progress dicts while pulling a model."""
    with requests.post(
        _ollama_url() + "/api/pull",
        json={"name": tag, "stream": True},
        stream=True,
        timeout=None,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8"))
            except Exception:
                continue


def ollama_delete(tag: str) -> None:
    r = requests.delete(_ollama_url() + "/api/delete", json={"name": tag}, timeout=15)
    if r.status_code not in (200, 404):
        r.raise_for_status()


def _ollama_chat_json(model: str, system: str, user: str, temperature: float) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_ctx": 4096},
    }
    r = requests.post(_ollama_url() + "/api/chat", json=payload, timeout=180)
    if r.status_code == 404:
        raise BackendError(
            f"Model '{model}' is not installed in Ollama. Pull it from the Models tab."
        )
    r.raise_for_status()
    return r.json()["message"]["content"]


# --------------------------------------------------------------------------- #
# Generic OpenAI-compatible (vLLM / llama.cpp / LM Studio)
# --------------------------------------------------------------------------- #
def _openai_chat_json(model: str, system: str, user: str, temperature: float) -> str:
    base = settings.get("openai_base_url", "http://127.0.0.1:8000/v1").rstrip("/")
    key = settings.get("openai_api_key", "") or "not-needed"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(
        base + "/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {key}"},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def openai_available(timeout: float = 1.5) -> bool:
    base = settings.get("openai_base_url", "http://127.0.0.1:8000/v1").rstrip("/")
    key = settings.get("openai_api_key", "") or "not-needed"
    try:
        r = requests.get(base + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Mock (demo) backend – deterministic, keyword-aware, no model required
# --------------------------------------------------------------------------- #
def _seed(text: str) -> float:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _keyword_score(state: str, phrase: str) -> float:
    s = state.lower()
    words = [w for w in re.split(r"[^a-z0-9]+", phrase.lower()) if len(w) > 2]
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in s)
    return hits / len(words)


def _mock_chat_json(system: str, user: str) -> str:
    """Best-effort mock that reads the embedded question spec and produces plausible,
    deterministic probabilities so the UI works without any model installed."""
    state = ""
    m = re.search(r"STATE:\n(.*?)\n\nQUESTION", user, re.S)
    if m:
        state = m.group(1)
    # noul
    if '"probability"' in user:
        base = 0.35 + 0.3 * _seed(user)
        kw = _keyword_score(state, user)
        p = max(0.02, min(0.98, base + 0.2 * kw))
        return json.dumps({"probability": round(p, 3)})
    # choice / score -> list of options after "OPTIONS:"
    opts = re.findall(r"- \"(.*?)\":", user)
    if not opts:
        opts = re.findall(r"- (.+)", user)
    opts = [o.strip() for o in opts if o.strip()][:32]
    if not opts:
        return json.dumps({"probabilities": {}})
    raw = {}
    for o in opts:
        raw[o] = 0.15 + 0.7 * _seed(state + "::" + o) + 1.2 * _keyword_score(state, o)
    total = sum(raw.values()) or 1.0
    probs = {k: round(v / total, 4) for k, v in raw.items()}
    return json.dumps({"probabilities": probs})


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def active_backend() -> str:
    b = settings.get("backend", "ollama")
    if b == "ollama" and ollama_available():
        return "ollama"
    if b == "openai" and openai_available():
        return "openai"
    # graceful fallbacks
    if ollama_available():
        return "ollama"
    if openai_available():
        return "openai"
    return "mock"


def backend_status() -> dict:
    return {
        "configured": settings.get("backend"),
        "active": active_backend(),
        "ollama_available": ollama_available(),
        "ollama_url": _ollama_url(),
    }


def chat_json(system: str, user: str, model: Optional[str] = None,
              temperature: Optional[float] = None) -> tuple[str, str]:
    """Return (raw_json_text, backend_used)."""
    model = model or settings.get("model")
    temperature = settings.get("temperature", 0.0) if temperature is None else temperature
    backend = active_backend()
    if backend == "ollama":
        return _ollama_chat_json(model, system, user, temperature), "ollama"
    if backend == "openai":
        return _openai_chat_json(model, system, user, temperature), "openai"
    return _mock_chat_json(system, user), "mock"
