<div align="center">

# 🧠 real-JEV

**A local, open, typed-decision playground.**
Give it *context + typed questions*, get back *constrained answers with probabilities* — 100% on your own machine.


![status](https://img.shields.io/badge/runs-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![offline](https://img.shields.io/badge/private-runs%20offline-brightgreen)

</div>

---

## What is this?

Most LLM tools give you a chat box. **real-JEV is different** — it's a *decision engine*. You describe a situation (the **context / state**) and ask **typed questions**, and it returns structured answers with calibrated-ish probabilities and a confidence score. That's exactly what you want for routing, triage, classification, scoring, moderation and guardrails.

It runs a **small local model** (default: Qwen2.5 1.5B, which happily fits **4 GB of RAM on a CPU**) through [Ollama](https://ollama.com), so **everyone can use it** — no GPU or API bill required. Bigger models are one click away if you have the RAM or a GPU.

### Three question types (the "System One" primitives)

| Type | What it does | Returns |
|------|--------------|---------|
| **Choice** | Pick one option from a set | winning option + probability per option |
| **Score** | Rate against an ordered rubric (low → high) | chosen level + expected score |
| **Noul** | "How likely is *yes*?" | a single probability in `[0, 1]` |

---

## ✨ Features

- 🎮 **Playground tab** — type a context, build questions (choice / score / noul), hit **Run**, and see answers with probability bars + confidence.
- 📦 **Browse Models tab** — a curated catalog of small→large local models with RAM guidance. **Download**, **switch**, and **remove** models from the browser. Filter by how much RAM you have.
- 🌐 **Web Search tab** — paste a **Brave Search** or **Firecrawl** API key to give the model live internet access; results are fed into the context before it decides.
- 🔌 **Pluggable backend** — Ollama by default, or point it at any **OpenAI-compatible** server (vLLM, llama.cpp server, LM Studio).
- 🧩 **Wire-compatible API** — exposes `POST /v1/systemone` just like LocalJev, so existing tooling/SDKs can point at it.
- 🔒 **Private by default** — your context never leaves your machine unless *you* turn on web search.
- 🪄 **One command to run** — bootstraps its own virtualenv, installs deps, sets up Ollama, pulls a default model, and opens the browser for you.

---

## 🚀 Quick start

> **Prerequisite:** [Python 3.9+](https://www.python.org/downloads/) (that's it — the launcher handles the rest).

**macOS / Linux**
```bash
git clone https://github.com/yourname/real-jev.git
cd real-jev
./start.sh
```

**Windows** (double-click `start.bat`, or in a terminal):
```bat
git clone https://github.com/yourname/real-jev.git
cd real-jev
start.bat
```

**Or, on any OS:**
```bash
python run.py
```

The launcher will, **fully automatically**:
1. create a `.venv` and install Python dependencies,
2. install & start **Ollama** if it isn't already there — on Linux it downloads the
   official release (binary **+ native libraries**) into `~/.cache/real-jev` with **no
   `sudo` required**; on macOS it uses Homebrew; on Windows it uses `winget`,
3. detect your **RAM** and pull a model that fits (≤4 GB → `qwen2.5:0.5b`, 4–8 GB →
   `qwen2.5:1.5b`, 8–16 GB → `qwen2.5:3b`, 16 GB+ → `qwen2.5:7b`),
4. start the server and open **http://127.0.0.1:8080** 🎉

> **Nothing large is committed to the repo.** Every download URL lives in
> [`install.json`](install.json) and is fetched on first run, so the project itself
> stays tiny (~150 KB). Delete `~/.cache/real-jev` any time to reclaim the space; it
> will be re-installed on the next launch.

> **No model yet?** real-JEV still starts in **demo mode** so you can explore the whole UI — answers are simulated until you install a real model from the *Browse Models* tab.

### Launcher options
```bash
python run.py --help
python run.py --port 9000 --model qwen2.5:3b   # different port / default model
python run.py --no-browser                     # don't auto-open the browser
python run.py --no-pull                        # don't auto-download a model
python run.py --skip-ollama                    # use demo mode or a custom backend
```

---

## 🧠 Choosing a model for your machine

Open the **Browse Models** tab and set the *Max RAM* filter. Rough guidance:

| Your machine | Good picks |
|---|---|
| Old laptop / 4 GB RAM, CPU only | `qwen2.5:0.5b`, **`qwen2.5:1.5b`** (default), `llama3.2:1b` |
| 8 GB RAM or any GPU | `qwen2.5:3b`, `qwen3:4b`, `phi3.5`, `gemma2:2b` |
| 16 GB RAM / dedicated GPU | `qwen2.5:7b`, `mistral:7b` |

Smaller = faster & lighter but less accurate; larger = smarter but needs more memory. Download sizes and RAM needs are shown on each card.

---

## 🌐 Giving the model internet access (optional)

1. Get a free/cheap API key:
   - **Brave Search API** → https://api-dashboard.search.brave.com
   - **Firecrawl** → https://firecrawl.dev
2. Open the **Web Search** tab, pick the provider, paste the key, and **Save**.
3. Tick **Enable web search** (and/or the per-run checkbox in the Playground).

When enabled, real-JEV searches the web using your context + questions and injects the top results into the model's context before it decides. Keys are stored locally in `~/.real-jev/settings.json` (git-ignored).

---

## 🔌 Using the API directly

real-JEV is wire-compatible with LocalJev's endpoint:

```bash
curl http://127.0.0.1:8080/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "jev-latest",
    "state": "I was charged twice this month.",
    "questions": {
      "is_billing": { "type": "noul", "instructions": "Is this a billing issue?" },
      "team": {
        "type": "choice",
        "instructions": "Route to which team?",
        "criteria": { "billing": "money problems", "technical": "bugs", "sales": "pricing" }
      },
      "severity": {
        "type": "score",
        "instructions": "How severe is this?",
        "criteria": ["Minor", "Normal", "Urgent"]
      }
    }
  }'
```

Response (abridged):
```json
{
  "model": "qwen2.5:1.5b",
  "backend": "ollama",
  "answers": {
    "is_billing": { "type": "noul", "noul": 0.94, "confidence": 0.88 },
    "team": { "type": "choice", "choice": "billing", "probabilities": { "billing": 0.9, "technical": 0.06, "sales": 0.04 }, "confidence": 0.72 },
    "severity": { "type": "score", "score": "Normal", "expected_index": 1.1, "confidence": 0.4 }
  }
}
```

Other endpoints: `GET /ready`, `GET /api/status`, `GET /api/models`, `POST /api/models/pull`, `POST /api/models/select`, `GET|POST /api/settings`.

---

## 🏗️ How it works

```
Browser UI  ──►  FastAPI server  ──►  Jev engine  ──►  LLM backend (Ollama / OpenAI-compatible / mock)
 (tabs)          /v1/systemone        prompt + parse       small local model (Qwen, Llama, Gemma…)
                 /api/*               + normalize
                                      + confidence
                                          ▲
                                          └── optional web search (Brave / Firecrawl)
```

The engine turns each typed question into a compact JSON-probability prompt, asks the model (with `format: json`), validates and **retries malformed output**, normalizes the distribution, then computes the winning choice / expected score / noul and an **entropy-based confidence**. This mirrors LocalJev's "prompted probability" approach — the probabilities are *self-reported by the model*, not read from logits, so calibrate before using them for consequential decisions.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full breakdown.

---

## 📁 Project layout

```
real-jev/
├─ run.py               # one-command launcher (venv + Ollama + model + server)
├─ install.json         # all external download URLs (Ollama binary/libs, model tiers)
├─ start.sh / start.bat # OS shortcuts
├─ requirements.txt
├─ app/
│  ├─ server.py         # FastAPI: UI + REST + /v1/systemone
│  ├─ jev_engine.py     # the decision engine (prompt → probs → answers)
│  ├─ llm_backend.py    # Ollama / OpenAI-compatible / mock backends
│  ├─ web_search.py     # Brave / Firecrawl integration
│  ├─ catalog.py        # curated small-model catalog
│  ├─ settings.py       # persisted settings & API keys
│  └─ static/           # index.html + style.css + app.js (no build step)
└─ docs/ARCHITECTURE.md
```

---

## ❓ FAQ

**Do I need a GPU?** No. The default model runs on CPU with ~4 GB RAM.

**Is my data sent anywhere?** No — everything runs locally. Web search is the only feature that makes network calls, and only when you enable it.

**Can I use my existing Ollama models?** Yes — anything already pulled shows up in the Models tab automatically.

**vLLM / llama.cpp / LM Studio?** Yes — set the backend to *OpenAI-compatible* in the Web Search → Backend section and give it the base URL.

---

## 🙏 Credits & license

Inspired by [github/next **LocalJev**](https://github.com/githubnext/localjev) and TypeSafe AI's **Jev**. Not affiliated with or endorsed by either. Model hosting via [Ollama](https://ollama.com).

MIT — see [LICENSE](LICENSE).
