FROM python:3.12-slim as builder

WORKDIR /app

# Установка Poetry
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir poetry

# Копирование только файлов, необходимых для установки зависимостей
COPY pyproject.toml poetry.lock* ./

# Установка зависимостей
RUN poetry install --no-dev --no-interaction --no-ansi

# Второй этап для создания минимального образа
FROM python:3.12-slim

WORKDIR /app

# Копирование установленного виртуального окружения из предыдущего этапа
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Копирование кода приложения
COPY . .

# Установка переменных окружения для запуска
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Порт, который будет использовать приложение
EXPOSE 7860

# Запуск приложения
CMD ["python", "src/app.py"] 