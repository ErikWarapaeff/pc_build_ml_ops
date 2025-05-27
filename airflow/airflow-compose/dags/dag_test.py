from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from src.model_evaluator import main


default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    'retries': 1
}

with DAG(
    dag_id='testing_model',
    default_args=default_args,
    schedule=None,
    tags=['example']
) as dag:
    
    hello_task = PythonOperator(
        task_id='print_hello_task',
        python_callable=main
    )

hello_task