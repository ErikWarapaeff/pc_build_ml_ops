from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

try:
    # Используем ChatOpenAI, так как вся логика модели уже завёрнута в этот класс
    from langchain_openai import ChatOpenAI
except ImportError as err:  # pragma: no cover
    raise SystemExit(
        "Не удалось импортировать langchain-openai. Установите зависимости проекта (poetry install)."
    ) from err

CONFIG_PATH = Path("configs/api_service.yml")
DEFAULT_MODEL_NAME = "gpt-3.5-turbo"


class Settings(BaseModel):
    """Конфигурация API сервиса, читаемая из YAML или переменных окружения."""

    model_name: str = DEFAULT_MODEL_NAME
    temperature: float = 0.3
    max_tokens: int = 1024

    @classmethod
    def load(cls) -> Settings:
        # Приоритет: переменные окружения → YAML конфиг → значения по умолчанию
        cfg: dict[str, Any] = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

        # Переопределения через окружение (например, из docker-compose)
        if env_model := os.getenv("MODEL_NAME"):
            cfg["model_name"] = env_model
        if env_temp := os.getenv("TEMPERATURE"):
            cfg["temperature"] = float(env_temp)
        if env_max_tok := os.getenv("MAX_TOKENS"):
            cfg["max_tokens"] = int(env_max_tok)

        return cls(**cfg)


# Инициализируем FastAPI
app = FastAPI(title="PC-Build.AI — API сервиса модели", version="0.1.0")

# Разрешаем CORS (может потребоваться для фронтенда)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel):
    prompt: str
    model_name: str | None = None  # возможность выбрать модель в запросе


class PromptResponse(BaseModel):
    answer: str
    model_used: str
    duration: float


class EvaluationRequest(BaseModel):
    """Тело запроса для /evaluate."""

    # Опционально можно передать путь к конфигу и базе, но по умолчанию используются стандартные
    config_path: str | None = None


class EvaluationResponse(BaseModel):
    evaluation_path: str
    results: dict[str, Any]
    duration: float


class CompareModelResult(BaseModel):
    model_name: str
    answer: str
    duration: float


class CompareRequest(BaseModel):
    prompt: str
    models: list[str]


class CompareResponse(BaseModel):
    prompt: str
    results: list[CompareModelResult]
    total_duration: float


@lru_cache(maxsize=10)
def _create_llm(model_name: str, temperature: float, max_tokens: int) -> ChatOpenAI:  # type: ignore[name-defined]
    """Создаёт (и кэширует) объект LLM для выбранной модели."""

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.vsegpt.ru/v1"),
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Проверка готовности контейнера."""

    return {"status": "ok"}


@app.post("/predict", response_model=PromptResponse)
async def predict(request: Request) -> PromptResponse:  # type: ignore[override]
    """Основная точка входа для получения ответа модели."""

    # --- Чтение и декодирование тела запроса ---
    body_bytes = await request.body()

    # Попытка декодирования/разбора JSON с несколькими кодировками (utf-8 → cp1251 → latin-1)
    last_error: Exception | None = None
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            payload = json.loads(body_bytes.decode(enc))  # type: ignore[arg-type]
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except json.JSONDecodeError as exc:
            # Файл декодировался, но не распарсился — это уже ошибка JSON, дальше пытаться бессмысленно
            raise HTTPException(status_code=400, detail=f"Неверный JSON: {exc}") from exc
    else:
        raise HTTPException(
            status_code=400, detail=f"Невозможно декодировать тело запроса: {last_error}"
        )

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Тело запроса должно быть JSON-объектом.")

    prompt_raw = str(payload.get("prompt", "")).strip()
    if not prompt_raw:
        raise HTTPException(status_code=422, detail="Поле prompt не может быть пустым.")

    model_name = payload.get("model_name") or Settings.load().model_name

    # Простейший препроцессинг: убираем лишние пробелы / переводы строк
    prompt_clean = " ".join(prompt_raw.split())

    settings = Settings.load()

    start = time.perf_counter()
    try:
        llm = _create_llm(model_name, settings.temperature, settings.max_tokens)
        # Используем invoke для единообразия с остальным кодом проекта
        answer = llm.invoke(prompt_clean)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Ошибка модели: {exc}") from exc
    duration = time.perf_counter() - start

    # Если ChatOpenAI вернул объект Message, достаём контент
    if hasattr(answer, "content"):
        answer_text = str(answer.content)
    else:
        answer_text = str(answer)

    return PromptResponse(answer=answer_text, model_used=model_name, duration=duration)


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(req: EvaluationRequest | None = None) -> EvaluationResponse:  # type: ignore[override]
    """Запуск model_evaluator для выбранной модели (из настроек/окружения)."""

    settings = Settings.load()
    model_name = settings.model_name

    config_path = req.config_path if req and req.config_path else "configs/config.yml"

    # Импортируем только при вызове, чтобы не тянуть тяжёлые зависимости при старте контейнера
    from src.model_evaluator import ModelEvaluator  # local import

    start_time = time.perf_counter()
    evaluator = ModelEvaluator(config_path)
    results_dict = evaluator.evaluate_models([model_name])
    duration = time.perf_counter() - start_time

    # Последний сохранённый файл располагается в evaluation_results/, получаем путь
    evaluation_dir = Path(__file__).resolve().parent.parent / "evaluation_results"
    latest_file: str = sorted(evaluation_dir.glob("model_evaluation_*.yml"))[-1].as_posix()

    return EvaluationResponse(evaluation_path=latest_file, results=results_dict, duration=duration)


@app.post("/compare", response_model=CompareResponse)
async def compare_models(req: CompareRequest) -> CompareResponse:  # type: ignore[override]
    """Возвращает ответы и время генерации для нескольких моделей за один запрос."""

    settings = Settings.load()

    results: list[CompareModelResult] = []
    start_total = time.perf_counter()

    for model_name in req.models:
        start = time.perf_counter()
        try:
            llm = _create_llm(model_name, settings.temperature, settings.max_tokens)
            answer = llm.invoke(req.prompt)
        except Exception as exc:
            answer_text = f"Ошибка модели: {exc}"
        else:
            # Получаем текст, если объект
            if hasattr(answer, "content"):
                answer_text = str(answer.content)
            else:
                answer_text = str(answer)
        duration = time.perf_counter() - start
        results.append(
            CompareModelResult(model_name=model_name, answer=answer_text, duration=duration)
        )

    total_duration = time.perf_counter() - start_total
    return CompareResponse(prompt=req.prompt, results=results, total_duration=total_duration)
