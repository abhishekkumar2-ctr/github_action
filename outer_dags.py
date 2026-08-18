from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def say_hello():
    print("Hello from outer_dags.py!")


default_args = {
    "owner": "data_platform_team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="outer_dags",
    description="Hello world DAG",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "hello"],
) as dag:

    hello_task = PythonOperator(
        task_id="say_hello",
        python_callable=say_hello,
    )
# test auto merge
