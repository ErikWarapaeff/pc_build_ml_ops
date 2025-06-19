import os
import time

import dvc.api
import mlflow
import pandas as pd
from dotenv import load_dotenv  # Загружаем переменные окружения из .env
from dvc.repo import Repo
from langchain_openai import ChatOpenAI  # Используем ChatOpenAI из langchain_openai

load_dotenv()
# Передаём ключ и базовый URL API в окружение
api_key = os.getenv("OPEN_AI_API_KEY")
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key
base_url = os.getenv("OPENAI_API_BASE", "https://api.vsegpt.ru/v1")
os.environ["OPENAI_API_BASE"] = base_url


def load_data():
    """Получает и загружает информацию о видеокартах из DVC-хранилища"""
    # Подтягиваем данные из удаленного хранилища DVC
    Repo().pull()
    # Используем файл с полной информацией о GPU
    path = "data/csv_files/gpu_full_info.csv"
    repo = "."
    with dvc.api.open(path, repo=repo, mode="r") as f:
        df = pd.read_csv(f)
    # Переименовываем столбец для совместимости с остальным кодом
    df = df.rename(columns={"gpu": "name"})
    return df


def run_experiments():
    """Проводит эксперименты по инференсу трех моделей и логирует результаты в MLflow"""
    df = load_data()
    os.makedirs("outputs", exist_ok=True)
    mlflow.set_experiment("pc_build_comparison")
    models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o-mini"]
    for model_name in models:
        llm = ChatOpenAI(model=model_name)
        with mlflow.start_run(run_name=model_name):
            prompt = f"Выбери первые 5 видеокарт с самой высокой ценой из списка: {', '.join(df['name'].head(10).tolist())}"
            start_time = time.time()
            # Используем invoke вместо устаревшего __call__
            result = llm.invoke(prompt)
            duration = time.time() - start_time
            # Логируем параметры и метрики
            mlflow.log_param("model_name", model_name)
            mlflow.log_metric("duration", duration)
            # Сохраняем и логируем артефакты
            output_path = f"outputs/{model_name}_output.txt"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"Prompt:\n{prompt}\n\nResult:\n{result}\n")
            mlflow.log_artifact(output_path)
    print("Experiments completed and logged to MLflow.")


if __name__ == "__main__":
    run_experiments()
