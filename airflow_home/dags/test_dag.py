from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def process_data():
    print("Processing data successfully!")


default_args = {
    "owner": "data_team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_example_pass",
    description="Example DAG for testing PR checks",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "test"],
) as dag:

    task_1 = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )