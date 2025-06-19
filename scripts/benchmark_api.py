#!/usr/bin/env python3
"""Быстрый бенчмарк HTTP-API сервисов моделей.

• Измеряет время ответа (latency) и длину сгенерированного текста.
• Сохраняет подробные результаты (JSON) и сводную таблицу (CSV, Markdown).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# Соответствие модель → порт контейнера FastAPI
MODEL_API_PORTS: dict[str, int] = {
    "gpt-3.5-turbo": 8001,
    "gpt-4o": 8002,
    "gpt-4o-mini": 8003,
}

# Стандартный набор вопросов (можно заменить, передав --dataset)
DEFAULT_QUESTIONS: list[str] = [
    "Привет, что ты умеешь?",
    "А какая средняя цена на видеокарты с поддержкой 4к?",
    "Мне нужен игровой ПК чтобы видеокарта поддерживала 4к, мой бюджет 200к",
    "А насколько в данной системе процессор раскрывает видеокарту?",
    "Хорошо, а пойдет ли на данной системе игра Cyberpunk 2077?",
    "Хорошо, найди мне тогда актуальные цены на данную систему.",
]


def load_questions(path: str | None) -> list[str]:
    if path is None:
        return DEFAULT_QUESTIONS
    p = Path(path)
    if not p.exists():
        print(f"Файл с датасетом не найден: {p}", file=sys.stderr)
        sys.exit(1)
    if p.suffix in {".txt"}:
        return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if p.suffix in {".json"}:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data]
    print("Неподдерживаемый формат датасета", file=sys.stderr)
    sys.exit(1)


def benchmark_model(model_name: str, questions: list[str]) -> dict[str, Any]:
    port = MODEL_API_PORTS.get(model_name)
    if port is None:
        raise ValueError(f"Неизвестный порт для модели {model_name}")
    url = f"http://localhost:{port}/predict"

    responses: list[dict[str, Any]] = []
    timings: list[float] = []
    lengths: list[int] = []  # длина ответа в словах

    for q in questions:
        start = time.perf_counter()
        resp = requests.post(url, json={"prompt": q})
        duration = time.perf_counter() - start
        timings.append(duration)

        if resp.status_code != 200:
            answer = f"ERROR {resp.status_code}: {resp.text[:200]}"
        else:
            try:
                answer = resp.json().get("answer", "")
            except ValueError:
                answer = resp.text

        # Вычисляем длину ответа в словах и сохраняем
        lengths.append(len(str(answer).split()))
        responses.append(
            {"question": q, "answer": answer, "time": duration, "length": len(answer.split())}
        )

    return {
        "model": model_name,
        "responses": responses,
        "timings": timings,
        "avg_length": sum(lengths) / len(lengths) if lengths else 0,
        "avg_time": sum(timings) / len(timings),
        "total_time": sum(timings),
    }


def save_results(results: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"api_benchmark_results_{timestamp}.json"
    summary_path_csv = out_dir / f"api_benchmark_summary_{timestamp}.csv"
    summary_path_md = out_dir / f"api_benchmark_summary_{timestamp}.md"

    # RAW
    json.dump(results, raw_path.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # SUMMARY
    rows = [
        {
            "model": r["model"],
            "avg_time_s": r["avg_time"],
            "total_time_s": r["total_time"],
            "avg_length_words": r.get("avg_length", 0),
        }
        for r in results
    ]
    df = pd.DataFrame(rows).sort_values("avg_time_s")
    df.to_csv(summary_path_csv, index=False, float_format="%.3f")

    # Markdown
    md = (
        "| Модель | Ср. время (с) | Общее время (с) | Ср. длина ответа (слов) |\n"
        "|-------|--------------|----------------|------------------------|\n"
    )
    for _, row in df.iterrows():
        md += (
            f"| {row['model']} | {row['avg_time_s']:.2f} | "
            f"{row['total_time_s']:.2f} | {row['avg_length_words']:.1f} |\n"
        )
    summary_path_md.write_text(md, encoding="utf-8")

    # --- Автоматическое обновление README.md ---
    _update_readme_with_benchmark(md)

    print(
        f"✔ Результаты сохранены:\n  RAW: {raw_path}\n  CSV: {summary_path_csv}\n  MD : {summary_path_md}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark HTTP-API моделей")
    parser.add_argument(
        "--models", nargs="+", default=list(MODEL_API_PORTS.keys()), help="Список моделей"
    )
    parser.add_argument("--dataset", type=str, help="Файл с вопросами (.txt или .json)")
    parser.add_argument(
        "--out", type=str, default="reports", help="Директория для сохранения отчётов"
    )
    args = parser.parse_args()

    questions = load_questions(args.dataset)

    all_results: list[dict[str, Any]] = []
    for model_name in args.models:
        print(f"→ Тестируем {model_name} ...")
        res = benchmark_model(model_name, questions)
        print(f"  Avg time: {res['avg_time']:.2f}s, total: {res['total_time']:.2f}s")
        all_results.append(res)

    save_results(all_results, Path(args.out))


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Вспомогательная util-функция: вставляет/обновляет секцию бенчмарка в README.md
# ---------------------------------------------------------------------------


def _update_readme_with_benchmark(table_md: str) -> None:  # pragma: no cover
    """Добавляет/обновляет секцию с результатами бенчмарка в README.md.

    Ищет маркеры `<!-- BENCHMARK_RESULTS_START -->` и `<!-- BENCHMARK_RESULTS_END -->`.
    Если они существуют — заменяет содержимое между ними. Если нет — добавляет
    новую секцию в конец README.md.
    """

    readme_path = Path("README.md")
    if not readme_path.exists():
        return

    start_marker = "<!-- BENCHMARK_RESULTS_START -->"
    end_marker = "<!-- BENCHMARK_RESULTS_END -->"

    content = readme_path.read_text(encoding="utf-8")

    section_md = (
        f"{start_marker}\n\n"
        f"## 🚀 Последние метрики моделей (обновлено {time.strftime('%Y-%m-%d %H:%M:%S')})\n\n"
        f"{table_md}\n\n"
        f"{end_marker}"
    )

    if start_marker in content and end_marker in content:
        # Заменяем существующую секцию
        pre = content.split(start_marker)[0]
        post = content.split(end_marker)[-1]
        new_content = pre + section_md + post
    else:
        # Просто добавляем в конец
        new_content = content.rstrip() + "\n\n" + section_md + "\n"

    readme_path.write_text(new_content, encoding="utf-8")
