"""Curated catalog of small, local-friendly models for real-JEV.

Each entry maps to an Ollama tag. `min_ram_gb` is a conservative estimate of the
system RAM you want *free* to run the model comfortably on CPU. Download sizes are
approximate (4-bit / Q4 quantized weights as shipped by Ollama).
"""

from __future__ import annotations

CATALOG = [
    {
        "tag": "qwen2.5:0.5b",
        "label": "Qwen2.5 0.5B Instruct",
        "family": "Qwen",
        "params": "0.5B",
        "download_gb": 0.4,
        "min_ram_gb": 2,
        "tier": "tiny",
        "notes": "Ultra-light. Runs on almost anything. Lower accuracy on tricky decisions.",
    },
    {
        "tag": "qwen2.5:1.5b",
        "label": "Qwen2.5 1.5B Instruct",
        "family": "Qwen",
        "params": "1.5B",
        "download_gb": 1.0,
        "min_ram_gb": 4,
        "tier": "default",
        "notes": "Recommended default. Great quality-for-size, fits 4 GB RAM on CPU.",
    },
    {
        "tag": "qwen3:1.7b",
        "label": "Qwen3 1.7B",
        "family": "Qwen",
        "params": "1.7B",
        "download_gb": 1.4,
        "min_ram_gb": 4,
        "tier": "small",
        "notes": "Newer Qwen3 generation. Strong reasoning for its size.",
    },
    {
        "tag": "llama3.2:1b",
        "label": "Llama 3.2 1B Instruct",
        "family": "Llama",
        "params": "1B",
        "download_gb": 1.3,
        "min_ram_gb": 4,
        "tier": "small",
        "notes": "Meta's tiny model. Fast on CPU.",
    },
    {
        "tag": "gemma2:2b",
        "label": "Gemma 2 2B Instruct",
        "family": "Gemma",
        "params": "2B",
        "download_gb": 1.6,
        "min_ram_gb": 6,
        "tier": "small",
        "notes": "Google Gemma 2. Good instruction following.",
    },
    {
        "tag": "qwen2.5:3b",
        "label": "Qwen2.5 3B Instruct",
        "family": "Qwen",
        "params": "3B",
        "download_gb": 1.9,
        "min_ram_gb": 8,
        "tier": "medium",
        "notes": "Noticeably better decisions. Comfortable with 8 GB RAM or any GPU.",
    },
    {
        "tag": "qwen3:4b",
        "label": "Qwen3 4B",
        "family": "Qwen",
        "params": "4B",
        "download_gb": 2.6,
        "min_ram_gb": 8,
        "tier": "medium",
        "notes": "Higher accuracy. Best with a GPU or 8 GB+ RAM.",
    },
    {
        "tag": "llama3.2:3b",
        "label": "Llama 3.2 3B Instruct",
        "family": "Llama",
        "params": "3B",
        "download_gb": 2.0,
        "min_ram_gb": 8,
        "tier": "medium",
        "notes": "Solid all-rounder from Meta.",
    },
    {
        "tag": "phi3.5:3.8b",
        "label": "Phi-3.5 Mini",
        "family": "Phi",
        "params": "3.8B",
        "download_gb": 2.2,
        "min_ram_gb": 8,
        "tier": "medium",
        "notes": "Microsoft Phi-3.5. Strong reasoning for size.",
    },
    {
        "tag": "qwen2.5:7b",
        "label": "Qwen2.5 7B Instruct",
        "family": "Qwen",
        "params": "7B",
        "download_gb": 4.7,
        "min_ram_gb": 16,
        "tier": "large",
        "notes": "High quality. Recommended with a GPU or 16 GB+ RAM.",
    },
    {
        "tag": "mistral:7b",
        "label": "Mistral 7B Instruct",
        "family": "Mistral",
        "params": "7B",
        "download_gb": 4.4,
        "min_ram_gb": 16,
        "tier": "large",
        "notes": "Popular 7B. Best on a GPU.",
    },
]

DEFAULT_MODEL = "qwen2.5:1.5b"


def catalog_map():
    return {m["tag"]: m for m in CATALOG}
