#!/usr/bin/env python
"""
Скрипт для форматирования Python кода с помощью Black.
Запуск: python format_code.py
"""

import subprocess
import sys


def main():
    """Форматирует Python файлы с помощью Black."""
    print("Запуск Black для форматирования кода...")

    # Проверяем, есть ли Poetry
    try:
        subprocess.run(["poetry", "--version"], check=True, capture_output=True)
        use_poetry = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        use_poetry = False

    # Формируем команду для Black
    if use_poetry:
        cmd = ["poetry", "run", "black", "src/"]
    else:
        cmd = ["black", "src/"]

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print("Black обнаружил проблемы с форматированием.")
            if input("Исправить автоматически? (y/n): ").lower() == "y":
                # Запускаем Black с опцией --quiet для применения изменений
                if use_poetry:
                    subprocess.run(["poetry", "run", "black", "src/"], check=True)
                else:
                    subprocess.run(["black", "src/"], check=True)
                print("Форматирование успешно применено.")
            else:
                print("Форматирование отменено.")
                sys.exit(1)
        else:
            print("Код уже отформатирован корректно.")
    except Exception as e:
        print(f"Ошибка при запуске Black: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
