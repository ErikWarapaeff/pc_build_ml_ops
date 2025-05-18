#!/usr/bin/env python3
# type: ignore

"""
Скрипт для подсчета токенов, используемых разными моделями,
и анализа их эффективности.
"""

import argparse
import logging
import os
import sys
import time
from typing import Any

import tiktoken
import yaml

# Настройка пути для импорта других модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model_evaluator import ModelEvaluator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class TokenCounter:
    """Класс для подсчета токенов и анализа эффективности моделей"""

    def __init__(self, results_dir: str):
        """
        Инициализация счетчика токенов

        Args:
            results_dir: Путь к директории с результатами тестирования
        """
        self.results_dir = results_dir
        self.model_encodings = {
            "gpt-3.5-turbo": "cl100k_base",
            "gpt-4": "cl100k_base",
            "gpt-4o": "cl100k_base",
            "gpt-4o-mini": "cl100k_base",
        }

    def _get_encoding_for_model(self, model_name: str):
        """
        Получение кодировщика токенов для модели

        Args:
            model_name: Название модели

        Returns:
            Кодировщик токенов
        """
        encoding_name = self.model_encodings.get(model_name, "cl100k_base")
        return tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str, model_name: str) -> int:
        """
        Подсчет количества токенов в тексте для конкретной модели

        Args:
            text: Текст для подсчета токенов
            model_name: Название модели

        Returns:
            Количество токенов
        """
        encoding = self._get_encoding_for_model(model_name)
        return len(encoding.encode(text))

    def analyze_results_file(self, results_file: str) -> dict[str, Any]:
        """
        Анализ результатов тестирования и подсчет токенов

        Args:
            results_file: Путь к файлу с результатами

        Returns:
            Словарь с результатами анализа
        """
        try:
            with open(results_file, encoding="utf-8") as f:
                results = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке результатов: {str(e)}")
            return {}

        token_analysis = {"models": [], "timestamp": results.get("timestamp", "")}

        for model_data in results.get("models", []):
            model_name = model_data.get("model", "unknown")
            model_analysis = {
                "model": model_name,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "token_efficiency": 0,
                "token_per_second": 0,
                "questions": [],
            }

            total_time = model_data.get("total_time", 0)
            responses = model_data.get("responses", [])

            for response_data in responses:
                question = response_data.get("question", "")
                answer = response_data.get("response", "")
                response_time = response_data.get("time", 0)

                input_tokens = self.count_tokens(question, model_name)
                output_tokens = self.count_tokens(answer, model_name)

                tokens_per_second = output_tokens / response_time if response_time > 0 else 0

                question_analysis = {
                    "question": question,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "time": response_time,
                    "tokens_per_second": tokens_per_second,
                }

                model_analysis["questions"].append(question_analysis)
                model_analysis["total_input_tokens"] += input_tokens
                model_analysis["total_output_tokens"] += output_tokens

            total_tokens = (
                model_analysis["total_input_tokens"] + model_analysis["total_output_tokens"]
            )
            model_analysis["token_efficiency"] = (
                model_analysis["total_output_tokens"] / total_tokens if total_tokens > 0 else 0
            )
            model_analysis["token_per_second"] = (
                model_analysis["total_output_tokens"] / total_time if total_time > 0 else 0
            )

            token_analysis["models"].append(model_analysis)

        return token_analysis

    def save_token_analysis(self, analysis: dict[str, Any]) -> None:
        """
        Сохранение результатов анализа токенов в файл

        Args:
            analysis: Результаты анализа
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        analysis_path = os.path.join(self.results_dir, f"token_analysis_{timestamp}.yml")

        try:
            with open(analysis_path, "w", encoding="utf-8") as f:
                yaml.dump(analysis, f, default_flow_style=False)
            logger.info(f"Анализ токенов сохранен в: {analysis_path}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении анализа токенов: {str(e)}")


def main():
    """Основная функция для запуска анализа токенов"""
    parser = argparse.ArgumentParser(description="Анализ использования токенов разными моделями")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="evaluation_results",
        help="Путь к директории с результатами тестирования (по умолчанию: evaluation_results)",
    )
    parser.add_argument(
        "--results-file",
        type=str,
        help="Путь к конкретному файлу с результатами (если не указан, используется последний)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Уровень логирования (по умолчанию: INFO)",
    )
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

    args = parser.parse_args()

    # Настройка уровня логирования
    logger.setLevel(getattr(logging, args.log_level))

    # Проверка доступности директории с результатами
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.results_dir
    )
    os.makedirs(results_dir, exist_ok=True)

    token_counter = TokenCounter(results_dir)

    # Если указан конкретный файл с результатами
    if args.results_file:
        if not os.path.exists(args.results_file):
            logger.error(f"Файл с результатами не найден: {args.results_file}")
            sys.exit(1)

        logger.info(f"Анализ токенов для файла: {args.results_file}")
        analysis = token_counter.analyze_results_file(args.results_file)
        token_counter.save_token_analysis(analysis)
    else:
        # Запуск тестирования моделей, если файл не указан
        logger.info(f"Запуск тестирования моделей: {', '.join(args.models)}")
        evaluator = ModelEvaluator(args.config)
        results = evaluator.evaluate_models(args.models)

        # Сохранение результатов тестирования
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        results_path = os.path.join(results_dir, f"model_evaluation_{timestamp}.yml")
        with open(results_path, "w", encoding="utf-8") as f:
            yaml.dump(results, f, default_flow_style=False)

        # Анализ токенов для полученных результатов
        logger.info("Анализ токенов для результатов тестирования моделей")
        analysis = token_counter.analyze_results_file(results_path)
        token_counter.save_token_analysis(analysis)


if __name__ == "__main__":
    main()
