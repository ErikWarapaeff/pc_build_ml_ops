from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
}

with DAG(
    'docker_file_extraction',
    default_args=default_args,
    schedule_interval=None,
) as dag:

    run_container = DockerOperator(
        task_id='run_docker_container',
        image='your-docker-image:latest',  # Замените на ваш образ
        command='python /app/your_script.py',  # Команда внутри контейнера
        volumes=['/host/output_dir:/container/output'],  # Смонтированный том
        docker_url='unix:///var/run/docker.sock',  # URL Docker Engine
        auto_remove=True,  # Автоочистка контейнера после выполнения
    )
