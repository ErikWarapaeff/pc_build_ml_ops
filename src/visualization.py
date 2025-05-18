#!/usr/bin/env python3

"""
Скрипт для визуализации результатов тестирования различных моделей
в мультиагентной системе.
"""

import argparse
import glob
import logging
import os
import sys
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import yaml

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ResultsVisualizer:
    """Класс для визуализации результатов тестирования моделей"""

    def __init__(self, results_dir: str):
        """
        Инициализация визуализатора результатов

        Args:
            results_dir: Путь к директории с результатами
        """
        self.results_dir = results_dir

    def load_results(self, results_file: str) -> dict[str, Any] | None:
        """
        Загрузка результатов из файла

        Args:
            results_file: Путь к файлу с результатами

        Returns:
            Словарь с результатами или None в случае ошибки
        """
        try:
            with open(results_file, encoding="utf-8") as f:
                results = yaml.safe_load(f)
            return results
        except Exception as e:
            logger.error(f"Ошибка при загрузке результатов из {results_file}: {str(e)}")
            return None

    def find_latest_results(self) -> str | None:
        """
        Поиск последнего файла с результатами

        Returns:
            Путь к последнему файлу с результатами или None, если файлы не найдены
        """
        # Поиск всех файлов с результатами
        result_files = glob.glob(os.path.join(self.results_dir, "model_evaluation_*.yml"))

        if not result_files:
            logger.error(f"Файлы с результатами не найдены в {self.results_dir}")
            return None

        # Сортировка по времени модификации (от новых к старым)
        result_files.sort(key=os.path.getmtime, reverse=True)

        return result_files[0]

    def visualize_response_times(self, results: dict[str, Any], output_dir: str) -> None:
        """
        Визуализация времени ответа для разных моделей

        Args:
            results: Словарь с результатами тестирования
            output_dir: Директория для сохранения визуализаций
        """
        if not results or "models" not in results:
            logger.error("Неверный формат результатов")
            return

        # Создаем директорию для сохранения визуализаций
        os.makedirs(output_dir, exist_ok=True)

        # Извлекаем данные для визуализации
        model_names = []
        avg_response_times = []
        total_times = []

        for model_data in results["models"]:
            model_name = model_data["model"]
            timings = model_data["timings"]
            total_time = model_data["total_time"]

            model_names.append(model_name)
            avg_response_times.append(sum(timings) / len(timings))
            total_times.append(total_time)

        # Создаем визуализацию среднего времени ответа
        plt.figure(figsize=(10, 6))
        plt.bar(model_names, avg_response_times, color="skyblue")
        plt.xlabel("Модель")
        plt.ylabel("Среднее время ответа (сек.)")
        plt.title("Сравнение среднего времени ответа разных моделей")
        plt.xticks(rotation=45)
        plt.tight_layout()

        avg_time_path = os.path.join(output_dir, "avg_response_time.png")
        plt.savefig(avg_time_path)
        logger.info(f"Сохранена визуализация среднего времени ответа: {avg_time_path}")

        # Создаем визуализацию общего времени выполнения
        plt.figure(figsize=(10, 6))
        plt.bar(model_names, total_times, color="lightgreen")
        plt.xlabel("Модель")
        plt.ylabel("Общее время выполнения (сек.)")
        plt.title("Сравнение общего времени выполнения разных моделей")
        plt.xticks(rotation=45)
        plt.tight_layout()

        total_time_path = os.path.join(output_dir, "total_time.png")
        plt.savefig(total_time_path)
        logger.info(f"Сохранена визуализация общего времени выполнения: {total_time_path}")

        # Создаем визуализацию времени ответа на каждый вопрос
        plt.figure(figsize=(12, 8))

        # Получаем все вопросы
        questions = [f"Q{i+1}" for i in range(len(results["models"][0]["timings"]))]

        # Подготавливаем данные
        data = {}
        for model_data in results["models"]:
            model_name = model_data["model"]
            data[model_name] = model_data["timings"]

        # Создаем DataFrame
        df = pd.DataFrame(data, index=questions)

        # Создаем визуализацию
        df.plot(kind="bar", figsize=(12, 8), width=0.8)
        plt.xlabel("Вопрос")
        plt.ylabel("Время ответа (сек.)")
        plt.title("Время ответа на каждый вопрос для разных моделей")
        plt.legend(title="Модель")
        plt.tight_layout()

        questions_time_path = os.path.join(output_dir, "questions_response_time.png")
        plt.savefig(questions_time_path)
        logger.info(
            f"Сохранена визуализация времени ответа на каждый вопрос: {questions_time_path}"
        )

    def generate_report(self, results: dict[str, Any], output_dir: str) -> None:
        """
        Генерация отчета в формате HTML

        Args:
            results: Словарь с результатами тестирования
            output_dir: Директория для сохранения отчета
        """
        if not results or "models" not in results:
            logger.error("Неверный формат результатов")
            return

        # Создаем директорию для сохранения отчета
        os.makedirs(output_dir, exist_ok=True)

        # Генерируем HTML-отчет с использованием только timestamp
        timestamp = results["timestamp"]

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Отчет о тестировании моделей</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    color: #333;
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-bottom: 20px;
                }}
                th, td {{
                    text-align: left;
                    padding: 8px;
                    border: 1px solid #ddd;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .chart {{
                    margin: 20px 0;
                }}
                .question {{
                    margin-bottom: 20px;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
                .model-section {{
                    margin-bottom: 30px;
                    padding: 15px;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    background-color: #f8f9fa;
                }}
            </style>
        </head>
        <body>
            <h1>Отчет о тестировании моделей</h1>
            <p>Дата тестирования: {timestamp}</p>

            <h2>Сводная информация</h2>
            <table>
                <tr>
                    <th>Модель</th>
                    <th>Общее время (сек.)</th>
                    <th>Среднее время ответа (сек.)</th>
                </tr>
        """

        # Добавляем информацию о каждой модели
        for model_data in results["models"]:
            model_name = model_data["model"]
            total_time = model_data["total_time"]
            avg_time = sum(model_data["timings"]) / len(model_data["timings"])

            html += f"""
                <tr>
                    <td>{model_name}</td>
                    <td>{total_time:.2f}</td>
                    <td>{avg_time:.2f}</td>
                </tr>
            """

        html += """
            </table>

            <h2>Визуализации</h2>
            <div class="chart">
                <h3>Среднее время ответа</h3>
                <img src="avg_response_time.png" alt="Среднее время ответа" width="100%">
            </div>
            <div class="chart">
                <h3>Общее время выполнения</h3>
                <img src="total_time.png" alt="Общее время выполнения" width="100%">
            </div>
            <div class="chart">
                <h3>Время ответа на каждый вопрос</h3>
                <img src="questions_response_time.png" alt="Время ответа на каждый вопрос" width="100%">
            </div>

            <h2>Детальные результаты</h2>
        """

        # Добавляем детальную информацию о каждой модели
        for model_data in results["models"]:
            model_name = model_data["model"]

            html += f"""
            <div class="model-section">
                <h3>Модель: {model_name}</h3>
                <p>Общее время выполнения: {model_data["total_time"]:.2f} сек.</p>
                <p>Среднее время ответа: {sum(model_data["timings"]) / len(model_data["timings"]):.2f} сек.</p>

                <h4>Ответы на вопросы:</h4>
            """

            # Добавляем информацию о каждом вопросе и ответе
            for i, response_data in enumerate(model_data["responses"]):
                question = response_data["question"]
                response = response_data["response"]
                time = response_data["time"]

                html += f"""
                <div class="question">
                    <p><strong>Вопрос {i+1}:</strong> {question}</p>
                    <p><strong>Ответ:</strong> {response}</p>
                    <p><strong>Время ответа:</strong> {time:.2f} сек.</p>
                </div>
                """

            html += """
            </div>
            """

        html += """
        </body>
        </html>
        """

        # Сохраняем отчет
        report_path = os.path.join(output_dir, "report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Сохранен HTML-отчет: {report_path}")


def main():
    """Основная функция для запуска визуализации результатов"""
    parser = argparse.ArgumentParser(description="Визуализация результатов тестирования моделей")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="evaluation_results",
        help="Директория с результатами тестирования (по умолчанию: evaluation_results)",
    )
    parser.add_argument(
        "--results-file",
        type=str,
        default=None,
        help="Конкретный файл с результатами (если не указан, будет использован последний)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation_results/visualizations",
        help="Директория для сохранения визуализаций (по умолчанию: evaluation_results/visualizations)",
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

    # Проверка доступности директории с результатами
    if not os.path.exists(args.results_dir):
        logger.error(f"Директория с результатами не найдена: {args.results_dir}")
        sys.exit(1)

    # Инициализация визуализатора результатов
    visualizer = ResultsVisualizer(args.results_dir)

    # Определение файла с результатами
    results_file = args.results_file
    if not results_file:
        results_file = visualizer.find_latest_results()
        if not results_file:
            logger.error("Не найдены файлы с результатами тестирования")
            sys.exit(1)

    # Загрузка результатов
    logger.info(f"Загрузка результатов из файла: {results_file}")
    results = visualizer.load_results(results_file)

    if not results:
        logger.error("Не удалось загрузить результаты тестирования")
        sys.exit(1)

    # Создание визуализаций
    logger.info("Создание визуализаций")
    visualizer.visualize_response_times(results, args.output_dir)

    # Генерация отчета
    logger.info("Генерация HTML-отчета")
    visualizer.generate_report(results, args.output_dir)

    logger.info(f"Визуализации и отчет сохранены в директории: {args.output_dir}")


if __name__ == "__main__":
    main()
