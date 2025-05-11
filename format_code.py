#!/usr/bin/env python
"""
Скрипт для форматирования Python кода с помощью Black и isort.
Запуск: python format_code.py
"""

import subprocess
import sys


def main():
    """Форматирует Python файлы с помощью Black и isort."""
    print("Запуск форматирования кода...")

    # Проверяем, есть ли Poetry
    try:
        subprocess.run(["poetry", "--version"], check=True, capture_output=True)
        use_poetry = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        use_poetry = False

    # Запускаем Black
    print("Запуск Black...")
    if use_poetry:
        black_cmd = ["poetry", "run", "black", "src/"]
    else:
        black_cmd = ["black", "src/"]

    try:
        black_result = subprocess.run(black_cmd, check=False)
        if black_result.returncode != 0:
            print("Black обнаружил проблемы с форматированием.")
            if input("Исправить автоматически? (y/n): ").lower() == "y":
                # Запускаем Black для применения изменений
                subprocess.run(black_cmd, check=True)
                print("Форматирование Black успешно применено.")
            else:
                print("Форматирование Black отменено.")
                sys.exit(1)
        else:
            print("Код уже отформатирован корректно с помощью Black.")
    except Exception as e:
        print(f"Ошибка при запуске Black: {e}")
        sys.exit(1)

    # Запускаем isort
    print("Запуск isort...")
    if use_poetry:
        isort_cmd = ["poetry", "run", "isort", "."]
    else:
        isort_cmd = ["isort", "."]

    try:
        isort_result = subprocess.run(isort_cmd, check=False)
        if isort_result.returncode != 0:
            print("isort обнаружил проблемы с сортировкой импортов.")
            if input("Исправить автоматически? (y/n): ").lower() == "y":
                # Запускаем isort для применения изменений
                subprocess.run(isort_cmd, check=True)
                print("Сортировка импортов успешно применена.")
            else:
                print("Сортировка импортов отменена.")
                sys.exit(1)
        else:
            print("Импорты уже отсортированы корректно с помощью isort.")
    except Exception as e:
        print(f"Ошибка при запуске isort: {e}")
        sys.exit(1)

    print("Форматирование кода успешно завершено!")


if __name__ == "__main__":
    main()
