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
    
    testing_different_model = PythonOperator(
        task_id='testing_different_model',
        python_callable=main
    )

testing_different_model