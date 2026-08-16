"""
dag_2.py
Example DAG that uses an external library (pandas) so CI proves
requirements.txt installation works correctly.
"""
from datetime import datetime, timedelta

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator


def process_data():
    df = pd.DataFrame({"col_a": [1, 2, 3], "col_b": [4, 5, 6]})
    df["sum"] = df["col_a"] + df["col_b"]
    print(df)


default_args = {
    "owner": "data_platform_team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_2_pandas_demo",
    description="Demo DAG that uses pandas",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "pandas"],
) as dag:

    process_task = PythonOperator(
        task_id="process_data",
        python_callable=process_data,
    )
