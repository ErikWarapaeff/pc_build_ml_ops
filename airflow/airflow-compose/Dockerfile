FROM apache/airflow:3.0.1
USER airflow
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY configs configs
USER airflow