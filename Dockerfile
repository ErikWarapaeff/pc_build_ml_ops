# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.2

# Установка Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" && poetry config virtualenvs.create false

WORKDIR /app

# Копируем файлы управления зависимостями
COPY pyproject.toml poetry.lock* ./

# Устанавливаем зависимости
RUN poetry install --no-root --only main

# Копируем исходный код проекта
COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api_service:app", "--host", "0.0.0.0", "--port", "8000"]
