from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def print_hello():
    print("Hello from Airflow!")

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    'retries': 1
}

with DAG(
    dag_id='simple_dag',
    default_args=default_args,
    schedule_interval='@daily',
    tags=['example']
) as dag:
    
    hello_task = PythonOperator(
        task_id='print_hello_task',
        python_callable=print_hello
    )

hello_task