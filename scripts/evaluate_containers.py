#!/usr/bin/env python3
"""Запускает эндпойнт /evaluate на каждом контейнере и сохраняет результаты."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

SERVICES: dict[str, str] = {
    "gpt-3.5-turbo": "http://localhost:8001/evaluate",
    "gpt-4o": "http://localhost:8002/evaluate",
    "gpt-4o-mini": "http://localhost:8003/evaluate",
}

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

overall: list[dict[str, object]] = []

for model_name, url in SERVICES.items():
    print(f"Running evaluation on {model_name} ({url}) ...")
    start = time.perf_counter()
    resp = requests.post(url, timeout=3600)  # evaluation может быть длительной
    elapsed = time.perf_counter() - start
    if resp.status_code != 200:
        print(f"Error for {model_name}: {resp.status_code} {resp.text}")
        continue
    data = resp.json()
    overall.append({"model": model_name, "elapsed": elapsed, **data})

json_path = REPORT_DIR / "evaluation_overall.json"
json_path.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Saved overall evaluation to {json_path}")
