#!/usr/bin/env python3
# type: ignore
# ruff: noqa: E402
"""
Скрипт для тестирования различных моделей в мультиагентной системе
с использованием базы данных из DVC.
"""

import os
import sys
from pathlib import Path

# Настройка пути для импорта других модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импорты после настройки sys.path
import argparse
import json  # Для сохранения результатов эксперимента
import logging
import time
from typing import Any

import mlflow
import yaml
from dvc.repo import Repo

from src.chat_backend import ChatBot  # type: ignore
from src.load_config import LoadConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Вспомогательная функция: вставляет/обновляет секцию результатов в README.md
# ---------------------------------------------------------------------------


def _update_readme_with_summary(table_md: str) -> None:  # pragma: no cover
    """Обновляет или вставляет секцию с результатами бенчмарка в README.md.

    Используются маркеры <!-- EVAL_RESULTS_START --> и <!-- EVAL_RESULTS_END -->.
    """
    readme = Path("README.md")
    if not readme.exists():
        return

    start_marker = "<!-- EVAL_RESULTS_START -->"
    end_marker = "<!-- EVAL_RESULTS_END -->"

    content = readme.read_text(encoding="utf-8")
    section = (
        f"{start_marker}\n\n"
        f"## 📊 Последние результаты оценки моделей (обновлено {time.strftime('%Y-%m-%d %H:%M:%S')})\n\n"
        f"{table_md}\n\n"
        f"{end_marker}"
    )

    if start_marker in content and end_marker in content:
        pre = content.split(start_marker)[0]
        post = content.split(end_marker)[-1]
        new_content = pre + section + post
    else:
        new_content = content.rstrip() + "\n\n" + section + "\n"

    readme.write_text(new_content, encoding="utf-8")


class ModelEvaluator:
    """Класс для тестирования и оценки различных моделей в мультиагентной системе"""

    def __init__(self, config_path: str, use_api: bool = False):
        """
        Инициализация оценщика моделей

        Args:
            config_path: Путь к конфигурационному файлу
            use_api: Флаг использования HTTP-API для опроса моделей
        """
        self.config_path = config_path
        self.original_config = self._load_config()
        self.test_questions = self._prepare_test_questions()
        self.use_api = use_api  # True → опрашиваем модель через HTTP-API
        # Подтягиваем данные из DVC перед тестированием (если работаем локально)
        if not self.use_api:
            Repo().pull()

    def _load_config(self) -> dict[str, Any]:
        """Загрузка конфигурации из файла"""
        if not os.path.exists(self.config_path):
            logger.error(f"Файл конфигурации не найден: {self.config_path}")
            sys.exit(1)

        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            # Убеждаемся, что результат соответствует типу Dict[str, Any]
            if not isinstance(config, dict):
                config = {}
            return config  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации: {str(e)}")
            sys.exit(1)

    def _save_config(self, config: dict[str, Any]) -> None:
        """Сохранение конфигурации в файл"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации: {str(e)}")

    def _prepare_test_questions(self) -> list[str]:
        """Подготовка списка тестовых вопросов для оценки моделей"""
        return [
            "Привет, что ты умеешь?",
            "А какая средняя цена на видеокарты с поддержкой 4к?",
            "Мне нужен игровой ПК чтобы видеокарта поддерживала 4к, мой бюджет 200к",
            "А насколько в данной системе процессор раскрывает видеокарту?",
            "Хорошо, а пойдет ли на данной системе игра Cyberpunk 2077?",
            "Хорошо, найди мне тогда актуальные цены на данную систему.",
        ]

    # --- Новый блок: запрос к модели через HTTP-API ---
    MODEL_API_PORTS: dict[str, int] = {
        "gpt-3.5-turbo": 8001,
        "gpt-4o": 8002,
        "gpt-4o-mini": 8003,
    }

    def _predict_via_api(self, model_name: str, prompt: str) -> tuple[str, float]:
        """Отправляет запрос к контейнеру модели и возвращает (ответ, время)."""

        import requests  # локальный импорт, чтобы не добавлять зависимость при оффлайн-режиме

        port = self.MODEL_API_PORTS.get(model_name)
        if port is None:
            raise ValueError(f"Неизвестный порт для модели {model_name}")

        url = f"http://localhost:{port}/predict"
        start = time.time()
        resp = requests.post(url, json={"prompt": prompt})
        duration = time.time() - start

        if resp.status_code != 200:
            raise RuntimeError(f"API {model_name} вернул {resp.status_code}: {resp.text[:200]}")

        try:
            answer = resp.json().get("answer", "")
        except ValueError:
            answer = resp.text
        return answer, duration

    def test_model(self, model_name: str) -> dict[str, Any]:
        """
        Тестирование одной модели на тестовых вопросах

        Args:
            model_name: Название модели для тестирования

        Returns:
            Словарь с результатами тестирования
        """
        if not self.use_api:
            # Меняем модель в конфигурации
            config = self.original_config.copy()
            config["openai_models"]["model"] = model_name
            # Сохраняем новую конфигурацию и перезагружаем
            self._save_config(config)
            LoadConfig()
            chatbot: ChatBot | None = ChatBot()
        else:
            chatbot = None  # noqa: E501

        # Результаты тестирования
        results: dict[str, Any] = {
            "model": model_name,
            "responses": [],
            "timings": [],
            "total_time": 0,
        }

        # Запускаем тестирование
        logger.info(f"Тестирование модели: {model_name}")
        start_time_total = time.time()

        # Используем List для chat_history
        chat_history: list[tuple[str | None, str]] = []

        for i, question in enumerate(self.test_questions):
            logger.info(f"Вопрос {i+1}: {question}")

            # Замеряем время ответа
            start_time = time.time()

            # Получаем ответ от бота
            try:
                if self.use_api:
                    bot_response, response_time = self._predict_via_api(model_name, question)
                else:
                    _, chat_history_new, _ = chatbot.respond(chat_history, question)
                    chat_history = chat_history_new
                    bot_response = (
                        chat_history[-1].get("content")
                        if isinstance(chat_history[-1], dict)
                        else None
                    ) or "Нет ответа"
                    response_time = time.time() - start_time
            except Exception as e:
                logger.error(f"Ошибка при получении ответа: {str(e)}")
                bot_response = f"ОШИБКА: {str(e)}"
                response_time = time.time() - start_time

            # Записываем результаты
            if isinstance(results["responses"], list):
                results["responses"].append(
                    {"question": question, "response": bot_response, "time": response_time}
                )

            if isinstance(results["timings"], list):
                results["timings"].append(response_time)

            logger.info(f"Ответ получен за {response_time:.2f} секунд")

        end_time_total = time.time()
        total_time = end_time_total - start_time_total
        results["total_time"] = total_time

        logger.info(f"Тестирование модели {model_name} завершено за {total_time:.2f} секунд")

        if not self.use_api:
            # Возвращаем оригинальную конфигурацию
            self._save_config(self.original_config)
            LoadConfig()

        return results

    def evaluate_models(self, models: list[str]) -> dict[str, Any]:
        """
        Тестирование нескольких моделей и сравнение их результатов

        Args:
            models: Список названий моделей для тестирования

        Returns:
            Словарь с результатами тестирования всех моделей
        """
        # Настройка эксперимента MLflow
        mlflow.set_experiment("model_evaluation")
        evaluation_results: dict[str, Any] = {
            "models": [],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        for model_name in models:
            with mlflow.start_run(run_name=model_name):
                logger.info(f"Начало тестирования модели: {model_name}")
                # Тестируем модель и получаем результаты
                model_results = self.test_model(model_name)
                # Сохраняем полные результаты как артефакт
                artifact_file = f"model_results_{model_name}.json"
                with open(artifact_file, "w", encoding="utf-8") as f:
                    json.dump(model_results, f, ensure_ascii=False, indent=2)
                mlflow.log_artifact(artifact_file)
                # Логирование параметров и метрик
                mlflow.log_param("model_name", model_name)
                for idx, t in enumerate(model_results["timings"]):
                    mlflow.log_metric("response_time", t, step=idx)
                mlflow.log_metric("total_time", model_results["total_time"])
            # Конец MLflow запуска

            if isinstance(evaluation_results["models"], list):
                evaluation_results["models"].append(model_results)

            if not self.use_api:
                # Возвращаем оригинальную конфигурацию между тестами моделей
                self._save_config(self.original_config)
                from src.load_config import LoadConfig

                LoadConfig()

            logger.info(f"Завершено тестирование модели: {model_name}")

            # Небольшая пауза между тестированием моделей
            time.sleep(1)

        if not self.use_api:
            # Восстанавливаем исходную конфигурацию в конце тестирования
            self._save_config(self.original_config)
            from src.load_config import LoadConfig

            LoadConfig()

        # Сохраняем результаты
        self._save_evaluation_results(evaluation_results)
        self._save_summary(evaluation_results)

        return evaluation_results

    def _save_evaluation_results(self, results: dict[str, Any]) -> None:
        """Сохранение результатов тестирования в файл"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation_results"
        )

        os.makedirs(results_dir, exist_ok=True)

        results_path = os.path.join(results_dir, f"model_evaluation_{timestamp}.yml")

        try:
            with open(results_path, "w", encoding="utf-8") as f:
                yaml.dump(results, f, default_flow_style=False)
            logger.info(f"Результаты тестирования сохранены в: {results_path}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении результатов: {str(e)}")

    def _save_summary(self, evaluation_results: dict[str, Any]) -> None:
        """Формирует краткое резюме по среднему/общему времени и сохраняет CSV и Markdown."""

        import pandas as pd  # локальный импорт

        models_data = evaluation_results.get("models", [])
        if not isinstance(models_data, list):
            return

        rows: list[dict[str, Any]] = []
        for m in models_data:
            timings = m.get("timings", [])
            if not timings:
                continue

            # --- Новая метрика: средняя длина ответа (в словах) ---
            responses = m.get("responses", [])
            lengths = [
                len(str(r.get("response", "")).split()) for r in responses if isinstance(r, dict)
            ]
            avg_len = sum(lengths) / len(lengths) if lengths else 0

            rows.append(
                {
                    "model": m.get("model"),
                    "avg_time_s": sum(timings) / len(timings),
                    "total_time_s": m.get("total_time", 0),
                    "avg_length_words": avg_len,
                }
            )

        if not rows:
            return

        df = pd.DataFrame(rows).sort_values("avg_time_s")

        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = Path(__file__).resolve().parent.parent / "evaluation_results"
        out_dir.mkdir(exist_ok=True, parents=True)

        csv_path = out_dir / f"evaluation_summary_{ts}.csv"
        md_path = out_dir / f"evaluation_summary_{ts}.md"

        df.to_csv(csv_path, index=False, float_format="%.3f")

        md = (
            "| Модель | Ср. время (с) | Общее время (с) | Ср. длина ответа (слов) |\n"
            "|-------|--------------|----------------|------------------------|\n"
        )
        for _, row in df.iterrows():
            md += (
                f"| {row['model']} | {row['avg_time_s']:.2f} | "
                f"{row['total_time_s']:.2f} | {row['avg_length_words']:.1f} |\n"
            )
        md_path.write_text(md, encoding="utf-8")

        logger.info("Сводный файл сохранён: %s", csv_path)

        # Обновляем README.md актуальными результатами
        _update_readme_with_summary(md)


def main() -> None:
    """Основная функция для запуска тестирования моделей"""
    parser = argparse.ArgumentParser(description="Тестирование моделей в мультиагентной системе")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yml",
        help="Путь к конфигурационному файлу (по умолчанию: configs/config.yml)",
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        help="Список моделей для тестирования (по умолчанию: gpt-4o-mini gpt-4o gpt-3.5-turbo)",
    )
    parser.add_argument(
        "--database",
        type=str,
        default="data/databases/pc_accessories_2.db",
        help="Путь к базе данных (по умолчанию: data/databases/pc_accessories_2.db)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Уровень логирования (по умолчанию: INFO)",
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Запрашивать модели по HTTP-API вместо прямого вызова ChatBot",
    )

    args = parser.parse_args()

    # Настройка уровня логирования
    logger.setLevel(getattr(logging, args.log_level))

    # Проверка доступности базы данных
    if not os.path.exists(args.database):
        logger.error(f"База данных не найдена: {args.database}")
        sys.exit(1)

    # Проверка доступности конфигурационного файла
    if not os.path.exists(args.config):
        logger.error(f"Конфигурационный файл не найден: {args.config}")
        sys.exit(1)

    # Инициализация оценщика моделей
    evaluator = ModelEvaluator(args.config, use_api=args.use_api)

    # Запуск оценки моделей
    logger.info(f"Начало тестирования моделей: {', '.join(args.models)}")
    results = evaluator.evaluate_models(args.models)

    # Выводим краткую сводку результатов
    logger.info("Сводка результатов тестирования:")
    for model_result in results["models"]:
        model_name = model_result["model"]
        total_time = model_result["total_time"]
        avg_time = sum(model_result["timings"]) / len(model_result["timings"])

        logger.info(f"Модель: {model_name}")
        logger.info(f"  Общее время: {total_time:.2f} секунд")
        logger.info(f"  Среднее время ответа: {avg_time:.2f} секунд")

    logger.info("Тестирование моделей завершено")


if __name__ == "__main__":
    main()
