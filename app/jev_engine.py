"""The real-JEV decision engine.

Reimplements the core idea of GitHub Next's LocalJev: take program `state` plus a set
of typed questions and return constrained answers with probabilities, by prompting a
local model for a JSON probability vector, validating/retrying, normalizing, and
computing choices, expected scores, and entropy-based confidence.

Question primitives (matching the Jev "System One" shape):
  - choice : pick one option from `criteria` (a map of option -> description)
  - score  : an ordered rubric; `criteria` is an ordered list of levels
  - noul   : probability in [0, 1] that the answer to `instructions` is "yes"
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from . import llm_backend, settings, web_search

SYSTEM_PROMPT = (
    "You are a precise decision engine. You read a STATE (context) and a typed "
    "QUESTION, then output ONLY a JSON object with calibrated probabilities. "
    "Do not explain. Do not add prose. Output valid JSON only. Probabilities are "
    "your best estimate and, for choices/scores, must sum to about 1.0. "
    "Commit to a decision: put clearly more probability on the single best-fitting "
    "option and less on the others. Do NOT return equal/uniform values."
)


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
def _choice_prompt(state: str, q: dict) -> tuple[str, list[str]]:
    criteria = q.get("criteria") or {}
    if isinstance(criteria, list):
        criteria = {c: "" for c in criteria}
    options = list(criteria.keys())
    lines = [f"STATE:\n{state}", "", "QUESTION (choice):", q.get("instructions", "")]
    lines.append("\nOPTIONS:")
    for opt, desc in criteria.items():
        lines.append(f'- "{opt}": {desc}' if desc else f'- "{opt}":')
    lines.append(
        "\nReturn JSON: {\"probabilities\": {"
        + ", ".join(f'"{o}": <0..1>' for o in options)
        + "}} — values must sum to 1, be clearly different, and put the most probability "
        "on the single best option."
    )
    return "\n".join(lines), options


def _score_prompt(state: str, q: dict) -> tuple[str, list[str]]:
    criteria = q.get("criteria") or []
    if isinstance(criteria, dict):
        levels = list(criteria.keys())
    else:
        levels = list(criteria)
    lines = [f"STATE:\n{state}", "", "QUESTION (score, ordered low -> high):", q.get("instructions", "")]
    lines.append("\nOPTIONS:")
    for i, lvl in enumerate(levels):
        lines.append(f'- "{lvl}": level {i}')
    lines.append(
        "\nReturn JSON: {\"probabilities\": {"
        + ", ".join(f'"{o}": <0..1>' for o in levels)
        + "}} — values must sum to 1, be clearly different, and put the most probability "
        "on the single best-matching level."
    )
    return "\n".join(lines), levels


def _noul_prompt(state: str, q: dict) -> str:
    lines = [
        f"STATE:\n{state}",
        "",
        "QUESTION (noul = probability of yes):",
        q.get("instructions", ""),
        "\nReturn JSON: {\"probability\": <0..1>} — the probability the answer is YES.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# JSON parsing / repair
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # strip code fences
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Could not parse JSON from model output: {text[:200]!r}")


def _normalize(probs: dict[str, float]) -> dict[str, float]:
    clean = {}
    for k, v in probs.items():
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        clean[k] = max(0.0, fv)
    total = sum(clean.values())
    if total <= 0:
        n = len(clean) or 1
        return {k: 1.0 / n for k in clean}
    return {k: v / total for k, v in clean.items()}


def _entropy_confidence(probs: list[float]) -> float:
    n = len(probs)
    if n <= 1:
        return 1.0
    h = -sum(p * math.log(p) for p in probs if p > 0)
    hmax = math.log(n)
    return round(1.0 - (h / hmax if hmax else 0.0), 4)


# --------------------------------------------------------------------------- #
# Per-question resolution (with corrective retries)
# --------------------------------------------------------------------------- #
def _norm_key(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _resolve_distribution(prompt: str, options: list[str], model, temperature, retries: int):
    last_err = None
    lookup = {_norm_key(o): o for o in options}
    for attempt in range(retries + 1):
        p = prompt if attempt == 0 else prompt + "\n\nIMPORTANT: your previous reply was invalid. Output ONLY the JSON object described above."
        raw, backend = llm_backend.chat_json(SYSTEM_PROMPT, p, model=model, temperature=temperature)
        try:
            data = _extract_json(raw)
            probs = data.get("probabilities") or data.get("probs") or data.get("distribution") or {}
            if not isinstance(probs, dict) or not probs:
                # Maybe the model returned {option: prob} at the top level
                probs = {k: v for k, v in data.items() if isinstance(v, (int, float, str))}
            # Map onto declared options using tolerant (case/space/punct-insensitive) keys
            mapped = {o: 0.0 for o in options}
            for k, v in probs.items():
                opt = lookup.get(_norm_key(k))
                if opt is not None:
                    try:
                        mapped[opt] = float(v)
                    except (TypeError, ValueError):
                        pass
            if sum(mapped.values()) <= 0:
                raise ValueError("all-zero distribution")
            return _normalize(mapped), backend, raw
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise ValueError(f"Model did not return a valid distribution after retries: {last_err}")


def _resolve_noul(prompt: str, model, temperature, retries: int):
    last_err = None
    for attempt in range(retries + 1):
        p = prompt if attempt == 0 else prompt + "\n\nIMPORTANT: output ONLY {\"probability\": <0..1>}."
        raw, backend = llm_backend.chat_json(SYSTEM_PROMPT, p, model=model, temperature=temperature)
        try:
            data = _extract_json(raw)
            val = data.get("probability", data.get("noul", data.get("yes")))
            fv = float(val)
            fv = max(0.0, min(1.0, fv))
            return fv, backend, raw
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise ValueError(f"Model did not return a valid probability after retries: {last_err}")


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def system_one(state: str, questions: dict[str, dict], model: str | None = None,
               use_web: bool | None = None) -> dict:
    model = model or settings.get("model")
    temperature = settings.get("temperature", 0.0)
    retries = 2

    web_used = False
    web_results: list[dict] = []
    if use_web is None:
        use_web = settings.get("web_search_enabled", False)
    augmented_state = state
    if use_web:
        query_bits = [state] + [q.get("instructions", "") for q in questions.values()]
        query = " ".join(b for b in query_bits if b).strip()[:400]
        try:
            web_results = web_search.search(query)
            ctx = web_search.results_to_context(web_results)
            if ctx:
                augmented_state = state + "\n\n" + ctx
                web_used = True
        except Exception as e:  # noqa: BLE001
            web_results = [{"title": "Web search failed", "url": "", "snippet": str(e)}]

    answers: dict[str, Any] = {}
    choices: dict[str, Any] = {}
    scores: dict[str, Any] = {}
    nouls: dict[str, Any] = {}
    backend_used = "mock"

    for qid, q in questions.items():
        qtype = (q.get("type") or "choice").lower()
        if qtype == "noul":
            prompt = _noul_prompt(augmented_state, q)
            val, backend_used, raw = _resolve_noul(prompt, model, temperature, retries)
            confidence = round(abs(val - 0.5) * 2, 4)
            entry = {"type": "noul", "noul": round(val, 4), "confidence": confidence}
            answers[qid] = entry
            nouls[qid] = entry
        elif qtype == "score":
            prompt, levels = _score_prompt(augmented_state, q)
            dist, backend_used, raw = _resolve_distribution(prompt, levels, model, temperature, retries)
            ordered = [dist[l] for l in levels]
            expected_index = sum(i * p for i, p in enumerate(ordered))
            best_idx = max(range(len(levels)), key=lambda i: ordered[i])
            entry = {
                "type": "score",
                "score": levels[best_idx],
                "index": best_idx,
                "expected_index": round(expected_index, 4),
                "levels": levels,
                "probabilities": {l: round(dist[l], 4) for l in levels},
                "confidence": _entropy_confidence(ordered),
            }
            answers[qid] = entry
            scores[qid] = entry
        else:  # choice
            prompt, options = _choice_prompt(augmented_state, q)
            dist, backend_used, raw = _resolve_distribution(prompt, options, model, temperature, retries)
            best = max(options, key=lambda o: dist[o])
            entry = {
                "type": "choice",
                "choice": best,
                "probabilities": {o: round(dist[o], 4) for o in options},
                "confidence": _entropy_confidence([dist[o] for o in options]),
            }
            answers[qid] = entry
            choices[qid] = entry

    return {
        "model": model,
        "backend": backend_used,
        "answers": answers,
        "choices": choices,
        "scores": scores,
        "nouls": nouls,
        "web_search": {"used": web_used, "results": web_results},
    }
