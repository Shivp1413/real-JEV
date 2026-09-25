"""real-JEV HTTP server: serves the web UI and the decision API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import catalog, jev_engine, llm_backend, settings, web_search

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="real-JEV", version="1.0.0")


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/ready")
def ready():
    st = llm_backend.backend_status()
    return {"ready": True, **st}


@app.get("/api/status")
def status():
    st = llm_backend.backend_status()
    installed = []
    if st["ollama_available"]:
        try:
            installed = llm_backend.ollama_list_models()
        except Exception:
            installed = []
    return {
        "backend": st,
        "model": settings.get("model"),
        "installed_models": installed,
        "web_search": {
            "enabled": settings.get("web_search_enabled"),
            "provider": settings.get("web_search_provider"),
        },
        "demo_mode": st["active"] == "mock",
    }


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def _run_decision(body: dict):
    state = body.get("state", "")
    questions = body.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=400, detail="No questions provided.")
    model = body.get("model")
    if model in (None, "", "jev-latest", "jev-preview"):
        model = settings.get("model")
    use_web = body.get("use_web")
    try:
        return jev_engine.system_one(state, questions, model=model, use_web=use_web)
    except llm_backend.BackendError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Decision failed: {e}")


@app.post("/v1/systemone")
async def system_one(request: Request):
    """Jev-compatible endpoint (matches LocalJev's request shape)."""
    body = await request.json()
    return _run_decision(body)


@app.post("/api/decide")
async def decide(request: Request):
    body = await request.json()
    return _run_decision(body)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@app.get("/api/models")
def models():
    st = llm_backend.backend_status()
    installed = {}
    if st["ollama_available"]:
        try:
            installed = {m["tag"]: m for m in llm_backend.ollama_list_models()}
        except Exception:
            installed = {}
    cat = []
    for m in catalog.CATALOG:
        entry = dict(m)
        entry["installed"] = m["tag"] in installed
        entry["active"] = m["tag"] == settings.get("model")
        cat.append(entry)
    # Include any installed models not in the catalog
    for tag, info in installed.items():
        if tag not in catalog.catalog_map():
            cat.append(
                {
                    "tag": tag,
                    "label": tag,
                    "family": "Installed",
                    "params": "?",
                    "download_gb": round((info.get("size_bytes") or 0) / 1e9, 2),
                    "min_ram_gb": "?",
                    "tier": "installed",
                    "notes": "Already installed in Ollama.",
                    "installed": True,
                    "active": tag == settings.get("model"),
                }
            )
    return {"models": cat, "active": settings.get("model"), "backend": st}


@app.post("/api/models/select")
async def select_model(request: Request):
    body = await request.json()
    tag = body.get("tag")
    if not tag:
        raise HTTPException(status_code=400, detail="Missing 'tag'.")
    settings.update({"model": tag})
    return {"ok": True, "model": tag}


@app.post("/api/models/pull")
async def pull_model(request: Request):
    body = await request.json()
    tag = body.get("tag")
    if not tag:
        raise HTTPException(status_code=400, detail="Missing 'tag'.")
    if not llm_backend.ollama_available():
        raise HTTPException(
            status_code=400,
            detail="Ollama is not running. Install it from ollama.com and run `ollama serve`.",
        )

    def gen():
        try:
            for ev in llm_backend.ollama_pull_stream(tag):
                yield json.dumps(ev) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/models/delete")
async def delete_model(request: Request):
    body = await request.json()
    tag = body.get("tag")
    if not tag:
        raise HTTPException(status_code=400, detail="Missing 'tag'.")
    try:
        llm_backend.ollama_delete(tag)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Settings / web search
# --------------------------------------------------------------------------- #
@app.get("/api/settings")
def get_settings():
    return settings.public_view()


@app.post("/api/settings")
async def post_settings(request: Request):
    body = await request.json()
    # Ignore masked key values (client only sends keys it wants to change)
    patch = {}
    allowed = {
        "backend", "ollama_url", "openai_base_url", "openai_api_key", "model",
        "temperature", "web_search_enabled", "web_search_provider",
        "brave_api_key", "firecrawl_api_key", "web_search_results",
    }
    for k, v in body.items():
        if k in allowed and v is not None and v != "":
            patch[k] = v
        # allow explicitly turning web search off (False is falsy)
        if k == "web_search_enabled":
            patch[k] = bool(v)
    settings.update(patch)
    return settings.public_view()


@app.post("/api/websearch/test")
async def test_websearch(request: Request):
    body = await request.json()
    query = body.get("query", "latest AI news")
    try:
        results = web_search.search(query)
        return {"ok": True, "results": results}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
