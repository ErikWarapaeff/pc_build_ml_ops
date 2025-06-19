#!/usr/bin/env python3
"""Скрипт для отправки запросов к запущенным Docker-сервисам моделей
и замера времени их ответа.

Пример использования:

    poetry run python scripts/benchmark.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

# Сервисы и их адреса. Портам должны соответствовать docker-compose.yml
SERVICES: dict[str, str] = {
    "gpt-3.5-turbo": "http://localhost:8001/predict",
    "gpt-4o": "http://localhost:8002/predict",
    "gpt-4o-mini": "http://localhost:8003/predict",
}

TEST_QUESTIONS: list[str] = [
    "Привет, что ты умеешь?",
    "А какая средняя цена на видеокарты с поддержкой 4к?",
    "Мне нужен игровой ПК, чтобы видеокарта поддерживала 4к, мой бюджет 200к",
]

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

results: list[dict[str, str | float]] = []

for model_name, url in SERVICES.items():
    for question in TEST_QUESTIONS:
        start = time.perf_counter()
        r = requests.post(url, json={"prompt": question})
        duration = time.perf_counter() - start
        if r.status_code != 200:
            answer = f"ERROR: {r.status_code} — {r.text}"
        else:
            answer = r.json().get("answer", "")
        results.append(
            {
                "model": model_name,
                "question": question,
                "answer": answer[:1000],  # усечём, чтобы не плодить огромные файлы
                "duration_sec": duration,
            }
        )
        print(f"[{model_name}] {duration:.2f}s — {question}")

# Сохраняем результаты в JSON и CSV
json_path = REPORT_DIR / "api_benchmark_results.json"
json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

try:
    import pandas as pd  # type: ignore

    df = pd.DataFrame(results)
    df.to_csv(REPORT_DIR / "api_benchmark_results.csv", index=False)
except ImportError:
    pass  # pandas не обязателен

print(f"Результаты сохранены в {json_path}")
