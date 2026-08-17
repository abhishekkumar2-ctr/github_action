"""
dag_3.py
Example DAG that uses requests library and shows task dependency chaining.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def fetch_status():
    import requests 
    print(f"requests library loaded, version: {requests.__version__}")


def transform():
    print("Transforming fetched data...")


def load():
    print("Loading data into destination...")


default_args = {
    "owner": "data_platform_team",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="dag_3_etl_demo",
    description="Demo ETL-style DAG using requests",
    default_args=default_args,
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "etl", "requests"],
) as dag:

    fetch_task = PythonOperator(
        task_id="fetch_status", 
        python_callable=fetch_status
        )
    transform_task = PythonOperator(
        task_id="transform", 
        python_callable=transform
        )
    load_task = PythonOperator(
        task_id="load", 
        python_callable=load
        )

    fetch_task >> transform_task >> load_task
