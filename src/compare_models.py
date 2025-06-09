import json
import os

import matplotlib.pyplot as plt
import mlflow
import pandas as pd


def load_run_metrics(experiment_name):
    """Загружает метрики duration для каждой модели из эксперимента MLflow"""
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise ValueError(f"Experiment {experiment_name} not found")
    experiment_id = experiment.experiment_id
    client = mlflow.tracking.MlflowClient()
    runs = client.search_runs([experiment_id], order_by=["metrics.duration ASC"])
    data = []
    for run in runs:
        # Используем имя запуска модели
        model_name = run.info.run_name
        if model_name is None:
            continue
        data.append(
            {
                "model_name": model_name,
                # Используем метрику total_time, которую логирует ModelEvaluator
                "duration": run.data.metrics.get("total_time"),
                # Сохраняем идентификатор запуска для загрузки артефактов
                "run_id": run.info.run_id,
            }
        )
    df = pd.DataFrame(data)
    return df


def plot_metrics(df):
    """Строит и сохраняет столбчатую диаграмму сравнения времени инференса"""
    plt.figure(figsize=(8, 6))
    plt.bar(df["model_name"], df["duration"], color="skyblue")
    plt.xlabel("Model")
    plt.ylabel("Duration (s)")
    plt.title("Сравнение времени инференса моделей")
    os.makedirs("reports", exist_ok=True)
    chart_path = "reports/duration_comparison.png"
    plt.savefig(chart_path)
    return chart_path


def main():
    experiment_name = "model_evaluation"
    df = load_run_metrics(experiment_name)
    chart_path = plot_metrics(df)
    table_path = "reports/metrics_summary.csv"
    df.to_csv(table_path, index=False)
    # Анализ ответов из артефактов JSON
    client = mlflow.tracking.MlflowClient()
    lengths = []
    for _, row in df.iterrows():
        run_id = row["run_id"]
        model = row["model_name"]
        temp_dir = f"reports/artifacts/{model}"
        os.makedirs(temp_dir, exist_ok=True)
        # Получаем список артефактов в корне запуска
        artifacts = client.list_artifacts(run_id, path="")
        json_artifact = None
        for art in artifacts:
            if (
                not art.is_dir
                and art.path.endswith(".json")
                and art.path.startswith(f"model_results_{model}")
            ):
                json_artifact = art.path
                break
        if not json_artifact:
            continue  # пропускаем, если JSON не найден
        # Скачиваем найденный JSON-артефакт
        client.download_artifacts(run_id, json_artifact, temp_dir)
        file_path = os.path.join(temp_dir, json_artifact)
        # Читаем JSON с помощью встроенного json
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        # Считаем среднюю длину ответов
        responses = data.get("responses", [])
        if responses:
            avg_len = sum(len(item.get("response", "")) for item in responses) / len(responses)
        else:
            avg_len = 0
        lengths.append({"model_name": model, "avg_response_length": avg_len})
    lengths_df = pd.DataFrame(lengths)
    # Строим график длины ответов
    plt.figure(figsize=(8, 6))
    plt.bar(lengths_df["model_name"], lengths_df["avg_response_length"], color="lightgreen")
    plt.xlabel("Model")
    plt.ylabel("Avg Response Length (chars)")
    plt.title("Сравнение средней длины ответов моделей")
    resp_chart = "reports/response_lengths.png"
    plt.savefig(resp_chart)
    # Сохраняем длины ответов
    lengths_path = "reports/response_lengths.csv"
    lengths_df.to_csv(lengths_path, index=False)
    print(
        f"График времени сохранён: {chart_path}, метрики: {table_path}, график длин ответов: {resp_chart}, длины ответов: {lengths_path}"
    )


if __name__ == "__main__":
    main()
