#!/usr/bin/env python3
# type: ignore

"""
Скрипт для генерации полного отчета о сравнении языковых моделей.
Интегрирует данные из тестирования, анализа токенов и визуализации.
"""

import argparse
import glob
import logging
import os
import sys
import time
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import yaml

# Настройка пути для импорта других модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model_evaluator import ModelEvaluator
from src.token_counter import TokenCounter
from src.visualization import ResultsVisualizer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ReportGenerator:
    """Класс для генерации полного отчета о сравнении моделей"""

    def __init__(self, results_dir: str, output_dir: str):
        """
        Инициализация генератора отчетов

        Args:
            results_dir: Путь к директории с результатами тестирования
            output_dir: Путь к директории для сохранения отчета
        """
        self.results_dir = results_dir
        self.output_dir = output_dir
        self.token_counter = TokenCounter(results_dir)
        self.visualizer = ResultsVisualizer(results_dir)

    def find_latest_files(self) -> dict[str, str]:
        """
        Поиск последних файлов результатов

        Returns:
            Словарь с путями к последним файлам
        """
        latest_files = {}

        # Поиск последнего файла тестирования моделей
        model_files = glob.glob(os.path.join(self.results_dir, "model_evaluation_*.yml"))
        if model_files:
            model_files.sort(key=os.path.getmtime, reverse=True)
            latest_files["model_evaluation"] = model_files[0]

        # Поиск последнего файла анализа токенов
        token_files = glob.glob(os.path.join(self.results_dir, "token_analysis_*.yml"))
        if token_files:
            token_files.sort(key=os.path.getmtime, reverse=True)
            latest_files["token_analysis"] = token_files[0]

        return latest_files

    def load_yaml_file(self, file_path: str) -> dict[str, Any]:
        """
        Загрузка данных из YAML-файла

        Args:
            file_path: Путь к файлу

        Returns:
            Словарь с данными из файла
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {file_path}: {str(e)}")
            return {}

    def create_combined_dataframe(
        self, model_data: dict[str, Any], token_data: dict[str, Any]
    ) -> pd.DataFrame:
        """
        Создание объединенного DataFrame с данными о моделях

        Args:
            model_data: Данные тестирования моделей
            token_data: Данные анализа токенов

        Returns:
            DataFrame с комбинированными данными
        """
        combined_data = []

        # Словарь с данными о токенах по модели
        token_info_by_model = {}
        for model_token_info in token_data.get("models", []):
            model_name = model_token_info.get("model", "")
            if model_name:
                token_info_by_model[model_name] = model_token_info

        # Объединение данных
        for model_info in model_data.get("models", []):
            model_name = model_info.get("model", "")
            if not model_name:
                continue

            model_row = {
                "model": model_name,
                "avg_response_time": sum(model_info.get("timings", []))
                / len(model_info.get("timings", [1])),
                "total_time": model_info.get("total_time", 0),
            }

            # Добавление данных о токенах
            if model_name in token_info_by_model:
                token_info = token_info_by_model[model_name]
                model_row.update(
                    {
                        "input_tokens": token_info.get("total_input_tokens", 0),
                        "output_tokens": token_info.get("total_output_tokens", 0),
                        "token_efficiency": token_info.get("token_efficiency", 0),
                        "tokens_per_second": token_info.get("token_per_second", 0),
                    }
                )

            combined_data.append(model_row)

        return pd.DataFrame(combined_data)

    def generate_comparison_charts(self, df: pd.DataFrame) -> dict[str, str]:
        """
        Генерация графиков сравнения моделей

        Args:
            df: DataFrame с данными о моделях

        Returns:
            Словарь с путями к созданным графикам
        """
        chart_files = {}
        os.makedirs(self.output_dir, exist_ok=True)

        # График времени ответа
        plt.figure(figsize=(10, 6))
        plt.bar(df["model"], df["avg_response_time"], color="skyblue")
        plt.xlabel("Модель")
        plt.ylabel("Среднее время ответа (с)")
        plt.title("Сравнение среднего времени ответа")
        plt.xticks(rotation=45)
        plt.tight_layout()

        time_chart_path = os.path.join(self.output_dir, "response_time_comparison.png")
        plt.savefig(time_chart_path)
        chart_files["response_time"] = time_chart_path

        # График эффективности токенов
        if "token_efficiency" in df.columns:
            plt.figure(figsize=(10, 6))
            plt.bar(df["model"], df["token_efficiency"], color="lightgreen")
            plt.xlabel("Модель")
            plt.ylabel("Эффективность токенов")
            plt.title("Сравнение эффективности использования токенов")
            plt.xticks(rotation=45)
            plt.tight_layout()

            token_chart_path = os.path.join(self.output_dir, "token_efficiency_comparison.png")
            plt.savefig(token_chart_path)
            chart_files["token_efficiency"] = token_chart_path

        # График производительности (токены в секунду)
        if "tokens_per_second" in df.columns:
            plt.figure(figsize=(10, 6))
            plt.bar(df["model"], df["tokens_per_second"], color="salmon")
            plt.xlabel("Модель")
            plt.ylabel("Токенов в секунду")
            plt.title("Сравнение производительности (токенов в секунду)")
            plt.xticks(rotation=45)
            plt.tight_layout()

            performance_chart_path = os.path.join(self.output_dir, "performance_comparison.png")
            plt.savefig(performance_chart_path)
            chart_files["performance"] = performance_chart_path

        return chart_files

    def get_model_recommendations(self, df: pd.DataFrame) -> dict[str, str]:
        """
        Формирование рекомендаций по выбору модели

        Args:
            df: DataFrame с данными о моделях

        Returns:
            Словарь с рекомендациями по различным аспектам
        """
        recommendations: dict[str, str] = {}

        if df.empty:
            return recommendations

        # Определение лучшей модели по скорости
        fastest_model = df.loc[df["avg_response_time"].idxmin()]["model"]
        recommendations["fastest"] = fastest_model

        # Определение лучшей модели по эффективности токенов
        if "token_efficiency" in df.columns:
            most_efficient_model = df.loc[df["token_efficiency"].idxmax()]["model"]
            recommendations["most_efficient"] = most_efficient_model

        # Определение лучшей модели по производительности
        if "tokens_per_second" in df.columns:
            most_productive_model = df.loc[df["tokens_per_second"].idxmax()]["model"]
            recommendations["most_productive"] = most_productive_model

        # Определение общей рекомендации по соотношению скорость/эффективность
        if "token_efficiency" in df.columns and "avg_response_time" in df.columns:
            # Нормализация значений
            df["norm_time"] = 1 - (df["avg_response_time"] - df["avg_response_time"].min()) / (
                df["avg_response_time"].max() - df["avg_response_time"].min()
            )
            if df["token_efficiency"].max() != df["token_efficiency"].min():
                df["norm_efficiency"] = (df["token_efficiency"] - df["token_efficiency"].min()) / (
                    df["token_efficiency"].max() - df["token_efficiency"].min()
                )
            else:
                df["norm_efficiency"] = 1

            # Общий балл (50% скорость, 50% эффективность)
            df["overall_score"] = 0.5 * df["norm_time"] + 0.5 * df["norm_efficiency"]
            best_overall_model = df.loc[df["overall_score"].idxmax()]["model"]
            recommendations["best_overall"] = best_overall_model

        return recommendations

    def generate_html_report(
        self,
        model_data: dict[str, Any],
        token_data: dict[str, Any],
        df: pd.DataFrame,
        charts: dict[str, str],
        recommendations: dict[str, str],
    ) -> str:
        """
        Генерация HTML-отчета о сравнении моделей

        Args:
            model_data: Данные тестирования моделей
            token_data: Данные анализа токенов
            df: DataFrame с обобщенными данными
            charts: Словарь с путями к графикам
            recommendations: Словарь с рекомендациями

        Returns:
            Путь к созданному HTML-файлу
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        report_timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Формирование таблицы с обобщенными данными
        table_html = df.to_html(classes="data-table", index=False, float_format="%.3f")

        # Формирование блока с рекомендациями
        recommendations_html = "<ul>"
        if "fastest" in recommendations:
            recommendations_html += (
                f"<li><strong>Самая быстрая модель:</strong> {recommendations['fastest']}</li>"
            )
        if "most_efficient" in recommendations:
            recommendations_html += f"<li><strong>Наиболее эффективная модель по использованию токенов:</strong> {recommendations['most_efficient']}</li>"
        if "most_productive" in recommendations:
            recommendations_html += f"<li><strong>Наиболее производительная модель (токенов в секунду):</strong> {recommendations['most_productive']}</li>"
        if "best_overall" in recommendations:
            recommendations_html += f"<li><strong>Лучшая модель по соотношению скорость/эффективность:</strong> {recommendations['best_overall']}</li>"
        recommendations_html += "</ul>"

        # Формирование блоков с графиками
        charts_html = ""
        for chart_name, chart_path in charts.items():
            chart_filename = os.path.basename(chart_path)
            charts_html += (
                f'<div class="chart"><img src="{chart_filename}" alt="{chart_name}"></div>'
            )

        # Формирование блока с деталями ответов моделей
        responses_html = ""
        for model_info in model_data.get("models", []):
            model_name = model_info.get("model", "")
            responses = model_info.get("responses", [])

            responses_html += f'<div class="model-section"><h3>Модель: {model_name}</h3>'
            responses_html += '<div class="responses">'

            for i, response in enumerate(responses):
                question = response.get("question", "")
                answer = response.get("response", "")
                response_time = response.get("time", 0)

                responses_html += '<div class="qa-pair">'
                responses_html += (
                    f'<div class="question"><strong>Вопрос {i+1}:</strong> {question}</div>'
                )
                responses_html += f'<div class="answer"><strong>Ответ:</strong> {answer}</div>'
                responses_html += f'<div class="time"><strong>Время ответа:</strong> {response_time:.2f} сек.</div>'

                # Добавление информации о токенах
                for token_model in token_data.get("models", []):
                    if token_model.get("model") == model_name and i < len(
                        token_model.get("questions", [])
                    ):
                        token_info = token_model["questions"][i]
                        responses_html += f'<div class="tokens"><strong>Токены запроса:</strong> {token_info.get("input_tokens", 0)}</div>'
                        responses_html += f'<div class="tokens"><strong>Токены ответа:</strong> {token_info.get("output_tokens", 0)}</div>'
                        responses_html += f'<div class="tokens"><strong>Токенов в секунду:</strong> {token_info.get("tokens_per_second", 0):.2f}</div>'

                responses_html += "</div>"

            responses_html += "</div></div>"

        # Формирование полного HTML-документа
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Отчет о сравнении языковых моделей</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    color: #333;
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                }}
                h1 {{
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                }}
                .data-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                .data-table th, .data-table td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                .data-table th {{
                    background-color: #f2f2f2;
                }}
                .data-table tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .recommendations {{
                    background-color: #e8f4f8;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .charts-container {{
                    display: flex;
                    flex-wrap: wrap;
                    justify-content: space-between;
                }}
                .chart {{
                    flex: 0 1 48%;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .chart img {{
                    max-width: 100%;
                    height: auto;
                }}
                .model-section {{
                    margin-bottom: 30px;
                    padding: 15px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
                .qa-pair {{
                    margin-bottom: 20px;
                    padding-bottom: 15px;
                    border-bottom: 1px dashed #ddd;
                }}
                .question, .answer, .time, .tokens {{
                    margin-bottom: 5px;
                }}
                .answer {{
                    white-space: pre-wrap;
                    background-color: #f8f9fa;
                    padding: 10px;
                    border-radius: 5px;
                }}
            </style>
        </head>
        <body>
            <h1>Отчет о сравнении языковых моделей</h1>
            <p><strong>Дата создания отчета:</strong> {timestamp}</p>

            <h2>Обзор результатов</h2>
            {table_html}

            <h2>Рекомендации</h2>
            <div class="recommendations">
                {recommendations_html}
            </div>

            <h2>Визуализация результатов</h2>
            <div class="charts-container">
                {charts_html}
            </div>

            <h2>Детальные результаты</h2>
            {responses_html}
        </body>
        </html>
        """

        # Сохранение HTML-отчета
        report_path = os.path.join(
            self.output_dir, f"model_comparison_report_{report_timestamp}.html"
        )
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"HTML-отчет сохранен в: {report_path}")

            # Копирование графиков в директорию отчета
            for chart_path in charts.values():
                chart_filename = os.path.basename(chart_path)
                with (
                    open(chart_path, "rb") as src_file,
                    open(os.path.join(self.output_dir, chart_filename), "wb") as dst_file,
                ):
                    dst_file.write(src_file.read())

        except Exception as e:
            logger.error(f"Ошибка при сохранении HTML-отчета: {str(e)}")

        return report_path

    def run_and_generate_report(
        self, models: list[str] | None = None, config_path: str | None = None
    ) -> str:
        """
        Запуск тестирования моделей и генерация отчета

        Args:
            models: Список моделей для тестирования
            config_path: Путь к конфигурационному файлу

        Returns:
            Путь к созданному отчету
        """
        if models and config_path:
            # Запуск тестирования моделей
            logger.info(f"Запуск тестирования моделей: {', '.join(models)}")
            evaluator = ModelEvaluator(config_path)
            model_results = evaluator.evaluate_models(models)

            # Анализ токенов
            model_results_path = os.path.join(
                self.results_dir, f"model_evaluation_{time.strftime('%Y%m%d_%H%M%S')}.yml"
            )
            with open(model_results_path, "w", encoding="utf-8") as f:
                yaml.dump(model_results, f, default_flow_style=False)

            token_analysis = self.token_counter.analyze_results_file(model_results_path)
            token_analysis_path = os.path.join(
                self.results_dir, f"token_analysis_{time.strftime('%Y%m%d_%H%M%S')}.yml"
            )
            with open(token_analysis_path, "w", encoding="utf-8") as f:
                yaml.dump(token_analysis, f, default_flow_style=False)

            # Визуализация результатов
            self.visualizer.visualize_response_times(model_results, self.output_dir)

            # Генерация отчета
            df = self.create_combined_dataframe(model_results, token_analysis)
            charts = self.generate_comparison_charts(df)
            recommendations = self.get_model_recommendations(df)
            report_path = self.generate_html_report(
                model_results, token_analysis, df, charts, recommendations
            )

            return report_path
        else:
            # Использование последних файлов результатов
            latest_files = self.find_latest_files()

            if not latest_files.get("model_evaluation") or not latest_files.get("token_analysis"):
                logger.error("Не найдены необходимые файлы с результатами")
                return ""

            logger.info("Использование существующих файлов результатов")

            model_data = self.load_yaml_file(latest_files["model_evaluation"])
            token_data = self.load_yaml_file(latest_files["token_analysis"])

            # Генерация отчета
            df = self.create_combined_dataframe(model_data, token_data)
            charts = self.generate_comparison_charts(df)
            recommendations = self.get_model_recommendations(df)
            report_path = self.generate_html_report(
                model_data, token_data, df, charts, recommendations
            )

            return report_path


def main():
    """Основная функция для запуска генерации отчета"""
    parser = argparse.ArgumentParser(description="Генерация отчета о сравнении языковых моделей")
    parser.add_argument(
        "--results-dir",
        type=str,
        default="evaluation_results",
        help="Путь к директории с результатами тестирования (по умолчанию: evaluation_results)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation_results/reports",
        help="Путь к директории для сохранения отчета (по умолчанию: evaluation_results/reports)",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Запустить тестирование моделей перед генерацией отчета",
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

    # Проверка доступности директорий
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.results_dir
    )
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.output_dir
    )

    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    report_generator = ReportGenerator(results_dir, output_dir)

    if args.run_tests:
        # Проверка доступности конфигурационного файла
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.config
        )
        if not os.path.exists(config_path):
            logger.error(f"Конфигурационный файл не найден: {config_path}")
            sys.exit(1)

        report_path = report_generator.run_and_generate_report(args.models, config_path)
    else:
        report_path = report_generator.run_and_generate_report()

    if report_path:
        logger.info(f"Отчет успешно создан: {report_path}")
    else:
        logger.error("Не удалось создать отчет")


if __name__ == "__main__":
    main()
