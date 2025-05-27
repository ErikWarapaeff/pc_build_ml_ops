#!/usr/bin/env python3

"""
Скрипт-обертка для запуска полного цикла тестирования языковых моделей.
Последовательно выполняет тестирование моделей, анализ токенов и генерацию отчета.
"""

import argparse
import logging
import os
import subprocess
import sys
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run_command(command: list[str]) -> bool:
    """
    Запуск команды с выводом в консоль

    Args:
        command: Список аргументов команды

    Returns:
        True, если команда выполнена успешно, False в случае ошибки
    """
    try:
        logger.info(f"Запуск команды: {' '.join(command)}")

        # Получаем директорию проекта для задания PYTHONPATH
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Создаем копию текущих переменных окружения
        env = os.environ.copy()

        # Добавляем корневую директорию проекта в PYTHONPATH
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{project_dir};{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = project_dir

        logger.info(f"PYTHONPATH установлен: {env['PYTHONPATH']}")

        # Запускаем процесс и ждем его завершения напрямую, чтобы избежать проблем с буфером
        result = subprocess.run(command, env=env, capture_output=True, text=True)

        # Выводим stdout и stderr
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(line)

        if result.stderr:
            for line in result.stderr.splitlines():
                logger.error(line)

        if result.returncode != 0:
            logger.error(f"Команда завершилась с ошибкой (код {result.returncode})")
            return False

        logger.info("Команда успешно выполнена")
        return True

    except Exception as e:
        logger.error(f"Ошибка при выполнении команды: {str(e)}")
        return False


def run_full_test(
    models: list[str],
    config_path: str,
    results_dir: str,
    output_dir: str,
    log_level: str = "INFO",
) -> bool:
    """
    Запуск полного цикла тестирования моделей

    Args:
        models: Список моделей для тестирования
        config_path: Путь к конфигурационному файлу
        results_dir: Директория для сохранения результатов
        output_dir: Директория для сохранения отчета
        log_level: Уровень логирования

    Returns:
        True, если все этапы выполнены успешно, False в случае ошибки
    """
    # Проверка наличия директорий
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Получаем абсолютные пути для корректной работы в subprocess
    abs_config_path = os.path.abspath(config_path)

    # 1. Тестирование моделей
    model_evaluator_cmd = [
        sys.executable,  # Используем текущий интерпретатор Python
        "-m",  # Запускаем как модуль, а не как скрипт
        "src.model_evaluator",  # Путь к модулю внутри пакета
        f"--config={abs_config_path}",
        f"--log-level={log_level}",
    ]
    model_evaluator_cmd.extend(["--models"] + models)

    if not run_command(model_evaluator_cmd):
        logger.error("Ошибка при тестировании моделей")
        return False

    # Поиск последнего файла с результатами
    result_files = [
        f
        for f in os.listdir(results_dir)
        if f.startswith("model_evaluation_") and f.endswith(".yml")
    ]
    if not result_files:
        logger.error("Не найдены результаты тестирования моделей")
        return False

    # Сортировка файлов по времени создания (от новых к старым)
    result_files.sort(reverse=True)
    latest_result = os.path.join(results_dir, result_files[0])
    logger.info(f"Найден файл с результатами: {latest_result}")

    # 2. Анализ токенов
    token_counter_cmd = [
        sys.executable,
        "-m",
        "src.token_counter",
        f"--results-file={latest_result}",
        f"--log-level={log_level}",
    ]

    if not run_command(token_counter_cmd):
        logger.error("Ошибка при анализе токенов")
        return False

    # 3. Генерация полного отчета
    generate_report_cmd = [
        sys.executable,
        "-m",
        "src.generate_report",
        f"--results-dir={results_dir}",
        f"--output-dir={output_dir}",
        f"--log-level={log_level}",
    ]

    if not run_command(generate_report_cmd):
        logger.error("Ошибка при генерации отчета")
        return False

    # Поиск созданного отчета
    report_files = [
        f
        for f in os.listdir(output_dir)
        if f.startswith("model_comparison_report_") and f.endswith(".html")
    ]
    if not report_files:
        logger.error("Не найден сгенерированный отчет")
        return False

    # Сортировка файлов по времени создания (от новых к старым)
    report_files.sort(reverse=True)
    latest_report = os.path.join(output_dir, report_files[0])
    logger.info(f"Отчет успешно создан: {latest_report}")

    return True


def main() -> None:
    """Основная функция для запуска полного цикла тестирования"""
    parser = argparse.ArgumentParser(
        description="Запуск полного цикла тестирования языковых моделей"
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        help="Список моделей для тестирования (по умолчанию: gpt-4o-mini gpt-4o gpt-3.5-turbo)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yml",
        help="Путь к конфигурационному файлу (по умолчанию: configs/config.yml)",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="evaluation_results",
        help="Директория для сохранения результатов тестирования (по умолчанию: evaluation_results)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation_results/reports",
        help="Директория для сохранения отчета (по умолчанию: evaluation_results/reports)",
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

    # Запуск полного цикла тестирования
    logger.info(f"Запуск полного цикла тестирования моделей: {', '.join(args.models)}")
    start_time = time.time()

    success = run_full_test(
        models=args.models,
        config_path=args.config,
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        log_level=args.log_level,
    )

    end_time = time.time()
    duration = end_time - start_time

    if success:
        logger.info(f"Полный цикл тестирования успешно завершен за {duration:.2f} секунд")
    else:
        logger.error(f"Полный цикл тестирования завершен с ошибками за {duration:.2f} секунд")
        sys.exit(1)


if __name__ == "__main__":
    main()
