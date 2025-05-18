#!/usr/bin/env python3

"""
Скрипт для тестирования различных моделей в мультиагентной системе
с использованием базы данных из DVC.
"""

import argparse
import logging
import os
import sys
import time
from typing import Any

import yaml

# Настройка пути для импорта других модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chat_backend import ChatBot
from src.load_config import LoadConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Класс для тестирования и оценки различных моделей в мультиагентной системе"""

    def __init__(self, config_path: str):
        """
        Инициализация оценщика моделей

        Args:
            config_path: Путь к конфигурационному файлу
        """
        self.config_path = config_path
        self.original_config = self._load_config()
        self.test_questions = self._prepare_test_questions()

    def _load_config(self) -> dict[str, Any]:
        """Загрузка конфигурации из файла"""
        if not os.path.exists(self.config_path):
            logger.error(f"Файл конфигурации не найден: {self.config_path}")
            sys.exit(1)

        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config
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

    def test_model(self, model_name: str) -> dict[str, Any]:
        """
        Тестирование одной модели на тестовых вопросах

        Args:
            model_name: Название модели для тестирования

        Returns:
            Словарь с результатами тестирования
        """
        # Меняем модель в конфигурации
        config = self.original_config.copy()
        config["openai_models"]["model"] = model_name

        # Сохраняем новую конфигурацию
        self._save_config(config)

        # Перезагружаем конфигурацию в системе
        LoadConfig()

        # Инициализируем чат-бота
        chatbot = ChatBot()

        # Результаты тестирования
        results = {"model": model_name, "responses": [], "timings": [], "total_time": 0}

        # Запускаем тестирование
        logger.info(f"Тестирование модели: {model_name}")
        start_time_total = time.time()

        chat_history: list[tuple[str | None, str]] = []

        for i, question in enumerate(self.test_questions):
            logger.info(f"Вопрос {i+1}: {question}")

            # Замеряем время ответа
            start_time = time.time()

            # Получаем ответ от бота
            # Здесь вызываем метод из ChatBot для получения ответа
            try:
                chat_history, response = chatbot.respond(chat_history, question)
                # Сохраняем последний ответ
                bot_response = chat_history[-1][1] if chat_history else "Нет ответа"
            except Exception as e:
                logger.error(f"Ошибка при получении ответа: {str(e)}")
                bot_response = f"ОШИБКА: {str(e)}"

            end_time = time.time()
            response_time = end_time - start_time

            # Записываем результаты
            results["responses"].append(
                {"question": question, "response": bot_response, "time": response_time}
            )

            results["timings"].append(response_time)

            logger.info(f"Ответ получен за {response_time:.2f} секунд")

        end_time_total = time.time()
        total_time = end_time_total - start_time_total
        results["total_time"] = total_time

        logger.info(f"Тестирование модели {model_name} завершено за {total_time:.2f} секунд")

        return results

    def evaluate_models(self, models: list[str]) -> dict[str, Any]:
        """
        Тестирование нескольких моделей и сравнение их результатов

        Args:
            models: Список названий моделей для тестирования

        Returns:
            Словарь с результатами тестирования всех моделей
        """
        evaluation_results = {"models": [], "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}

        for model_name in models:
            logger.info(f"Начало тестирования модели: {model_name}")
            model_results = self.test_model(model_name)
            evaluation_results["models"].append(model_results)

            # Возвращаем оригинальную конфигурацию между тестами моделей
            self._save_config(self.original_config)
            from src.load_config import LoadConfig

            LoadConfig()

            logger.info(f"Завершено тестирование модели: {model_name}")

            # Небольшая пауза между тестированием моделей
            time.sleep(1)

        # Восстанавливаем исходную конфигурацию в конце тестирования
        self._save_config(self.original_config)
        from src.load_config import LoadConfig

        LoadConfig()

        # Сохраняем результаты
        self._save_evaluation_results(evaluation_results)

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


def main():
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
    evaluator = ModelEvaluator(args.config)

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
