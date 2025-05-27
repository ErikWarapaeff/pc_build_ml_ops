#!/usr/bin/env python3

"""
Скрипт для проверки целостности и качества данных в базе данных,
находящейся под контролем DVC.
"""

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from typing import Any

import yaml

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DatabaseValidator:
    """Класс для проверки целостности и качества данных в базе данных"""

    def __init__(self, db_path: str):
        """
        Инициализация валидатора базы данных

        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None
        self.cursor: sqlite3.Cursor | None = None
        self.tables: list[str] = []
        self.total_checks = 0
        self.passed_checks = 0
        self.warnings = 0

    def connect(self) -> bool:
        """
        Подключение к базе данных

        Returns:
            True, если подключение успешно, иначе False
        """
        try:
            logger.info(f"Подключение к базе данных: {self.db_path}")
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подключении к базе данных: {str(e)}")
            return False

    def close(self) -> None:
        """Закрытие соединения с базой данных"""
        if self.connection:
            self.connection.close()
            logger.info("Соединение с базой данных закрыто")

    def get_tables(self) -> list[str]:
        """
        Получение списка таблиц в базе данных

        Returns:
            Список имен таблиц
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return []

        try:
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [
                table[0] for table in self.cursor.fetchall() if not table[0].startswith("sqlite_")
            ]
            logger.info(f"Найдены таблицы: {', '.join(tables)}")
            self.tables = tables
            return tables
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении списка таблиц: {str(e)}")
            return []

    def get_table_info(self, table_name: str) -> list[dict[str, Any]]:
        """
        Получение информации о столбцах таблицы

        Args:
            table_name: Имя таблицы

        Returns:
            Список словарей с информацией о столбцах
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return []

        try:
            self.cursor.execute(f"PRAGMA table_info([{table_name}]);")
            columns = []
            for column_info in self.cursor.fetchall():
                columns.append(
                    {
                        "id": column_info[0],
                        "name": column_info[1],
                        "type": column_info[2],
                        "notnull": column_info[3],
                        "default": column_info[4],
                        "pk": column_info[5],
                    }
                )
            return columns
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении информации о таблице {table_name}: {str(e)}")
            return []

    def count_records(self, table_name: str) -> Any:
        """
        Подсчет количества записей в таблице

        Args:
            table_name: Имя таблицы

        Returns:
            Количество записей в таблице
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return 0
        try:
            self.cursor.execute(f"SELECT COUNT(*) FROM [{table_name}];")
            result = self.cursor.fetchone()
            if result is None or result[0] is None:
                return 0
            count = result[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подсчете записей в таблице {table_name}: {str(e)}")
            return 0

    def check_null_values(self, table_name: str, column_name: str) -> tuple[int, int]:
        """
        Проверка на наличие NULL значений в столбце

        Args:
            table_name: Имя таблицы
            column_name: Имя столбца

        Returns:
            Кортеж (количество NULL значений, общее количество записей)
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return (0, 0)

        try:
            self.cursor.execute(
                f"SELECT COUNT(*) FROM [{table_name}] WHERE [{column_name}] IS NULL;"
            )
            null_count = self.cursor.fetchone()[0]

            self.cursor.execute(f"SELECT COUNT(*) FROM [{table_name}];")
            total_count = self.cursor.fetchone()[0]

            return (null_count, total_count)
        except sqlite3.Error as e:
            logger.error(
                f"Ошибка при проверке NULL значений в {table_name}.{column_name}: {str(e)}"
            )
            return (0, 0)

    def check_duplicate_values(self, table_name: str, column_name: str) -> tuple[int, int]:
        """
        Проверка на наличие дубликатов в столбце

        Args:
            table_name: Имя таблицы
            column_name: Имя столбца

        Returns:
            Кортеж (количество дубликатов, общее количество значений)
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return (0, 0)

        try:
            self.cursor.execute(
                f"""
                SELECT COUNT(*) - COUNT(DISTINCT [{column_name}])
                FROM [{table_name}]
                WHERE [{column_name}] IS NOT NULL;
            """
            )
            duplicate_count = self.cursor.fetchone()[0]

            self.cursor.execute(
                f"SELECT COUNT(*) FROM [{table_name}] WHERE [{column_name}] IS NOT NULL;"
            )
            total_count = self.cursor.fetchone()[0]

            return (duplicate_count, total_count)
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке дубликатов в {table_name}.{column_name}: {str(e)}")
            return (0, 0)

    def check_foreign_keys(self) -> bool:
        """
        Проверка внешних ключей в базе данных

        Returns:
            True, если проверка прошла успешно, иначе False
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return False

        try:
            self.cursor.execute("PRAGMA foreign_key_check;")
            violations = self.cursor.fetchall()

            if violations:
                logger.error(f"Найдены нарушения внешних ключей: {violations}")
                self.total_checks += 1
                return False
            else:
                logger.info("Проверка внешних ключей пройдена успешно")
                self.total_checks += 1
                self.passed_checks += 1
                return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при проверке внешних ключей: {str(e)}")
            self.total_checks += 1
            return False

    def check_data_ranges(
        self, table_name: str, column_name: str, column_type: str
    ) -> dict[str, Any]:
        """
        Проверка диапазона значений в столбце

        Args:
            table_name: Имя таблицы
            column_name: Имя столбца
            column_type: Тип данных столбца

        Returns:
            Словарь с информацией о диапазоне значений
        """
        if not self.cursor:
            logger.error("Нет подключения к базе данных")
            return {}

        result: dict[str, Any] = {
            "table": table_name,
            "column": column_name,
            "type": column_type,
            "min": "N/A",
            "max": "N/A",
            "avg": "N/A",
            "count": 0,
        }

        try:
            if column_type.upper() in [
                "INTEGER",
                "REAL",
                "NUMERIC",
                "FLOAT",
                "DOUBLE",
                "DECIMAL",
                "NUMBER",
            ]:
                self.cursor.execute(
                    f"""
                    SELECT
                        MIN([{column_name}]),
                        MAX([{column_name}]),
                        AVG([{column_name}]),
                        COUNT([{column_name}])
                    FROM [{table_name}]
                    WHERE [{column_name}] IS NOT NULL;
                """
                )
                data = self.cursor.fetchone()
                if data:
                    result["min"] = data[0] if data[0] is not None else "N/A"
                    result["max"] = data[1] if data[1] is not None else "N/A"
                    result["avg"] = data[2] if data[2] is not None else "N/A"
                    result["count"] = data[3] if data[3] is not None else 0
            elif column_type.upper() in ["TEXT", "VARCHAR", "CHAR", "STRING"]:
                self.cursor.execute(
                    f"""
                    SELECT
                        MIN(LENGTH([{column_name}])),
                        MAX(LENGTH([{column_name}])),
                        AVG(LENGTH([{column_name}])),
                        COUNT([{column_name}])
                    FROM [{table_name}]
                    WHERE [{column_name}] IS NOT NULL;
                """
                )
                data = self.cursor.fetchone()
                if data:
                    result["min_length"] = data[0] if data[0] is not None else "N/A"
                    result["max_length"] = data[1] if data[1] is not None else "N/A"
                    result["avg_length"] = data[2] if data[2] is not None else "N/A"
                    result["count"] = data[3] if data[3] is not None else 0

            return result
        except sqlite3.Error as e:
            logger.error(
                f"Ошибка при проверке диапазона значений в {table_name}.{column_name}: {str(e)}"
            )
            return result

    def validate_db(self, detailed: bool = False) -> dict[str, Any]:
        """
        Валидация базы данных

        Args:
            detailed: Флаг для включения подробного отчета

        Returns:
            Словарь с результатами валидации
        """
        validation_results: dict[str, Any] = {
            "database": os.path.basename(self.db_path),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tables": [],
        }

        # Получаем список таблиц
        tables = self.get_tables()
        if not tables:
            logger.warning("В базе данных нет таблиц или не удалось получить список таблиц")
            self.warnings += 1
            validation_results["tables"] = []
            validation_results["summary"] = {
                "total_tables": 0,
                "total_records": 0,
                "total_checks": self.total_checks,
                "passed_checks": self.passed_checks,
                "failed_checks": self.total_checks - self.passed_checks,
                "warnings": self.warnings,
            }
            return validation_results

        # Проверка внешних ключей
        foreign_keys_check = self.check_foreign_keys()
        validation_results["foreign_keys_check"] = "passed" if foreign_keys_check else "failed"

        # Проверка таблиц
        for table_name in tables:
            table_info: dict[str, Any] = {
                "name": table_name,
                "record_count": self.count_records(table_name),
                "columns": [],
                "issues": [],
            }

            columns = self.get_table_info(table_name)
            for column in columns:
                column_name = column["name"]
                column_type = column["type"]

                column_info: dict[str, Any] = {
                    "name": column_name,
                    "type": column_type,
                    "primary_key": column["pk"] == 1,
                    "not_null": column["notnull"] == 1,
                    "checks": [],
                }

                if column["notnull"] == 1:
                    self.total_checks += 1
                    null_count, total_count = self.check_null_values(table_name, column_name)
                    if null_count > 0:
                        column_info["checks"].append(
                            {
                                "type": "null_check",
                                "status": "failed",
                                "null_count": null_count,
                                "total_count": total_count,
                            }
                        )
                        table_info["issues"].append(
                            f"Столбец {column_name} содержит NULL значения ({null_count} из {total_count})"
                        )
                    else:
                        column_info["checks"].append(
                            {
                                "type": "null_check",
                                "status": "passed",
                            }
                        )
                        self.passed_checks += 1

                if column["pk"] == 1:
                    self.total_checks += 1
                    duplicate_count, total_count = self.check_duplicate_values(
                        table_name, column_name
                    )
                    if duplicate_count > 0:
                        column_info["checks"].append(
                            {
                                "type": "duplicate_check",
                                "status": "failed",
                                "duplicate_count": duplicate_count,
                                "total_count": total_count,
                            }
                        )
                        table_info["issues"].append(
                            f"Первичный ключ {column_name} содержит дубликаты ({duplicate_count})"
                        )
                    else:
                        column_info["checks"].append(
                            {
                                "type": "duplicate_check",
                                "status": "passed",
                            }
                        )
                        self.passed_checks += 1

                if detailed:
                    range_data = self.check_data_ranges(table_name, column_name, column_type)
                    if range_data:
                        column_info["range_data"] = range_data

                table_info["columns"].append(column_info)

            validation_results["tables"].append(table_info)

        validation_results["summary"] = {
            "total_tables": len(tables),
            "total_records": sum(table["record_count"] for table in validation_results["tables"]),
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.total_checks - self.passed_checks,
            "warnings": self.warnings,
        }

        self.close()
        return validation_results

    def save_results(self, results: dict[str, Any], output_file: str) -> None:
        """
        Сохранение результатов валидации в файл

        Args:
            results: Результаты валидации
            output_file: Путь к файлу для сохранения результатов
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                if output_file.endswith(".json"):
                    json.dump(results, f, ensure_ascii=False, indent=2)
                else:
                    yaml.dump(results, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Результаты валидации сохранены в: {output_file}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении результатов: {str(e)}")

    def generate_html_report(self, results: dict[str, Any], output_file: str) -> None:
        """
        Генерация HTML-отчета по результатам валидации

        Args:
            results: Результаты валидации
            output_file: Путь к файлу для сохранения HTML-отчета
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

            summary = results.get("summary", {})
            passed_ratio = (
                (summary.get("passed_checks", 0) / summary.get("total_checks", 1)) * 100
                if summary.get("total_checks", 0) > 0
                else 0
            )

            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Отчет о валидации базы данных</title>
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
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                    }}
                    th, td {{
                        text-align: left;
                        padding: 12px;
                        border: 1px solid #ddd;
                    }}
                    th {{
                        background-color: #f2f2f2;
                    }}
                    tr:nth-child(even) {{
                        background-color: #f9f9f9;
                    }}
                    .summary {{
                        background-color: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 5px solid #3498db;
                    }}
                    .success {{
                        color: #2ecc71;
                    }}
                    .warning {{
                        color: #f39c12;
                    }}
                    .error {{
                        color: #e74c3c;
                    }}
                    .progress-container {{
                        width: 100%;
                        background-color: #f1f1f1;
                        border-radius: 5px;
                        margin: 10px 0;
                    }}
                    .progress-bar {{
                        height: 30px;
                        background-color: #4CAF50;
                        border-radius: 5px;
                        text-align: center;
                        line-height: 30px;
                        color: white;
                    }}
                    .issues {{
                        background-color: #fff8e1;
                        padding: 10px;
                        border-left: 5px solid #ffc107;
                        margin: 10px 0;
                    }}
                </style>
            </head>
            <body>
                <h1>Отчет о валидации базы данных</h1>
                <p><strong>База данных:</strong> {results.get("database", "Неизвестно")}</p>
                <p><strong>Дата проверки:</strong> {results.get("timestamp", "Неизвестно")}</p>

                <h2>Сводка</h2>
                <div class="summary">
                    <p><strong>Всего таблиц:</strong> {summary.get("total_tables", 0)}</p>
                    <p><strong>Всего записей:</strong> {summary.get("total_records", 0)}</p>
                    <p><strong>Проведено проверок:</strong> {summary.get("total_checks", 0)}</p>
                    <p><strong>Успешных проверок:</strong> {summary.get("passed_checks", 0)}</p>
                    <p><strong>Неудачных проверок:</strong> {summary.get("failed_checks", 0)}</p>
                    <p><strong>Предупреждений:</strong> {summary.get("warnings", 0)}</p>

                    <div class="progress-container">
                        <div class="progress-bar" style="width: {passed_ratio}%;">
                            {passed_ratio:.1f}%
                        </div>
                    </div>
                </div>

                <h2>Результаты проверки внешних ключей</h2>
                <p class="{
                    'success' if results.get('foreign_keys_check') == 'passed' else 'error'
                }">
                    {
                        "Проверка внешних ключей прошла успешно"
                        if results.get('foreign_keys_check') == 'passed'
                        else "Обнаружены нарушения внешних ключей"
                    }
                </p>

                <h2>Проверки по таблицам</h2>
            """

            for table in results.get("tables", []):
                html += f"""
                <h3>Таблица: {table.get("name", "")}</h3>
                <p><strong>Количество записей:</strong> {table.get("record_count", 0)}</p>
                """

                if table.get("issues", []):
                    html += '<div class="issues"><h4>Проблемы:</h4><ul>'
                    for issue in table["issues"]:
                        html += f"<li>{issue}</li>"
                    html += "</ul></div>"

                html += """
                <table>
                    <tr>
                        <th>Столбец</th>
                        <th>Тип</th>
                        <th>Первичный ключ</th>
                        <th>Not Null</th>
                        <th>Проверки</th>
                    </tr>
                """

                for column in table.get("columns", []):
                    checks_html = ""
                    for check in column.get("checks", []):
                        if check.get("type") == "null_check":
                            if check.get("status") == "passed":
                                checks_html += (
                                    "<div class='success'>Проверка на NULL: Успешно</div>"
                                )
                            else:
                                checks_html += f"<div class='error'>Проверка на NULL: Ошибка ({check.get('null_count', 0)} из {check.get('total_count', 0)})</div>"
                        elif check.get("type") == "duplicate_check":
                            if check.get("status") == "passed":
                                checks_html += (
                                    "<div class='success'>Проверка на дубликаты: Успешно</div>"
                                )
                            else:
                                checks_html += f"<div class='error'>Проверка на дубликаты: Ошибка ({check.get('duplicate_count', 0)} дубликатов)</div>"

                    html += f"""
                    <tr>
                        <td>{column.get("name", "")}</td>
                        <td>{column.get("type", "")}</td>
                        <td>{"Да" if column.get("primary_key", False) else "Нет"}</td>
                        <td>{"Да" if column.get("not_null", False) else "Нет"}</td>
                        <td>{checks_html}</td>
                    </tr>
                    """

                html += "</table>"

                if any("range_data" in column for column in table.get("columns", [])):
                    html += """
                    <h4>Диапазоны данных</h4>
                    <table>
                        <tr>
                            <th>Столбец</th>
                            <th>Тип</th>
                            <th>Мин</th>
                            <th>Макс</th>
                            <th>Среднее</th>
                            <th>Количество</th>
                        </tr>
                    """

                    for column in table.get("columns", []):
                        if "range_data" in column:
                            range_data = column["range_data"]

                            if range_data["type"].upper() in [
                                "INTEGER",
                                "REAL",
                                "NUMERIC",
                                "FLOAT",
                                "DOUBLE",
                                "DECIMAL",
                                "NUMBER",
                            ]:
                                avg_value = range_data.get("avg")
                                avg_formatted = (
                                    f"{avg_value:.2f}" if avg_value is not None else "N/A"
                                )

                                html += f"""
                                <tr>
                                    <td>{range_data.get("column", "")}</td>
                                    <td>{range_data.get("type", "")}</td>
                                    <td>{range_data.get("min", "N/A")}</td>
                                    <td>{range_data.get("max", "N/A")}</td>
                                    <td>{avg_formatted}</td>
                                    <td>{range_data.get("count", 0)}</td>
                                </tr>
                                """
                            elif range_data["type"].upper() in [
                                "TEXT",
                                "VARCHAR",
                                "CHAR",
                                "STRING",
                            ]:
                                avg_length = range_data.get("avg_length")
                                avg_formatted = (
                                    f"{avg_length:.2f}" if avg_length is not None else "N/A"
                                )

                                html += f"""
                                <tr>
                                    <td>{range_data.get("column", "")}</td>
                                    <td>{range_data.get("type", "")}</td>
                                    <td>Мин. длина: {range_data.get("min_length", "N/A")}</td>
                                    <td>Макс. длина: {range_data.get("max_length", "N/A")}</td>
                                    <td>Средняя длина: {avg_formatted}</td>
                                    <td>{range_data.get("count", 0)}</td>
                                </tr>
                                """

                    html += "</table>"

            html += """
            </body>
            </html>
            """

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)

            logger.info(f"HTML-отчет сохранен в: {output_file}")
        except Exception as e:
            logger.error(f"Ошибка при генерации HTML-отчета: {str(e)}")


def check_dvc_status(db_path: str) -> str:
    """
    Проверка статуса DVC для базы данных

    Args:
        db_path: Путь к базе данных

    Returns:
        Текущий статус DVC (версия или хеш)
    """
    try:
        # Получение относительного пути от корня репозитория
        db_path = os.path.normpath(db_path)
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if os.path.isabs(db_path):
            rel_path = os.path.relpath(db_path, script_dir)
        else:
            rel_path = db_path

        # Проверка DVC статуса
        dvc_status_cmd = ["dvc", "status", rel_path]
        try:
            dvc_status_output = subprocess.check_output(
                dvc_status_cmd, stderr=subprocess.STDOUT, text=True
            )
            if "no recorded hash" in dvc_status_output.lower():
                logger.warning(f"База данных не находится под контролем DVC: {rel_path}")
                return "не под контролем DVC"
            elif "data item state changed" in dvc_status_output.lower():
                logger.warning(
                    f"Состояние базы данных отличается от сохраненного в DVC: {rel_path}"
                )
                return "изменена после сохранения в DVC"
            elif "everything is up to date" in dvc_status_output.lower():
                logger.info(f"База данных в актуальном состоянии в DVC: {rel_path}")
                return "актуальная версия"
        except subprocess.CalledProcessError:
            logger.warning(f"Не удалось получить DVC статус для {rel_path}")
            return "неизвестно"

        # Попытка получить хеш DVC
        dvc_info_cmd = ["dvc", "list", "--dvc-only", "--recursive", script_dir]
        try:
            dvc_info_output = subprocess.check_output(dvc_info_cmd, text=True)

            # Поиск информации о файле в выводе команды
            for line in dvc_info_output.splitlines():
                if rel_path in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return f"хеш: {parts[0]}"
        except subprocess.CalledProcessError:
            pass

        return "под контролем DVC"
    except Exception as e:
        logger.error(f"Ошибка при проверке DVC статуса: {str(e)}")
        return "ошибка проверки"


def main() -> None:
    """Основная функция для запуска валидации базы данных"""
    parser = argparse.ArgumentParser(description="Валидация базы данных под контролем DVC")
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/databases/pc_accessories_2.db",
        help="Путь к файлу базы данных (по умолчанию: data/databases/pc_accessories_2.db)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="validation_results",
        help="Директория для сохранения результатов валидации (по умолчанию: validation_results)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "yaml", "html", "all"],
        default="all",
        help="Формат вывода результатов (по умолчанию: all)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Включить подробный анализ данных",
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
    if not os.path.exists(args.db_path):
        logger.error(f"База данных не найдена: {args.db_path}")
        sys.exit(1)

    # Проверка статуса DVC
    logger.info("Проверка статуса DVC...")
    dvc_status = check_dvc_status(args.db_path)
    logger.info(f"Статус DVC: {dvc_status}")

    # Создание директории для результатов
    os.makedirs(args.output_dir, exist_ok=True)

    # Запуск валидации
    validator = DatabaseValidator(args.db_path)
    logger.info(f"Запуск валидации базы данных: {args.db_path}")

    start_time = time.time()
    validation_results = validator.validate_db(detailed=args.detailed)
    end_time = time.time()

    # Добавление информации о DVC
    validation_results["dvc_status"] = dvc_status
    validation_results["validation_time"] = end_time - start_time

    # Формирование имени файла для результатов
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename_base = f"{os.path.splitext(os.path.basename(args.db_path))[0]}_validation_{timestamp}"

    # Сохранение результатов
    if args.format == "json" or args.format == "all":
        json_file = os.path.join(args.output_dir, f"{filename_base}.json")
        validator.save_results(validation_results, json_file)

    if args.format == "yaml" or args.format == "all":
        yaml_file = os.path.join(args.output_dir, f"{filename_base}.yml")
        validator.save_results(validation_results, yaml_file)

    if args.format == "html" or args.format == "all":
        html_file = os.path.join(args.output_dir, f"{filename_base}.html")
        validator.generate_html_report(validation_results, html_file)

    # Вывод сводки
    summary = validation_results["summary"]
    logger.info("=== Сводка по валидации ===")
    logger.info(f"Проверено таблиц: {summary.get('total_tables', 0)}")
    logger.info(f"Проверено записей: {summary.get('total_records', 0)}")
    logger.info(f"Проведено проверок: {summary.get('total_checks', 0)}")
    logger.info(f"Успешных проверок: {summary.get('passed_checks', 0)}")
    logger.info(f"Неудачных проверок: {summary.get('failed_checks', 0)}")
    logger.info(f"Предупреждений: {summary.get('warnings', 0)}")
    logger.info(f"Статус DVC: {dvc_status}")
    logger.info(f"Время валидации: {end_time - start_time:.2f} сек.")

    # Возвращаем код ошибки, если есть неудачные проверки
    if summary.get("failed_checks", 0) > 0:
        logger.error("Валидация завершена с ошибками")
        sys.exit(1)
    else:
        logger.info("Валидация успешно завершена")


if __name__ == "__main__":
    main()
