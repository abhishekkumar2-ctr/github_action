# from datetime import datetime, timedelta

# from airflow import DAG
# from airflow.operators.python import PythonOperator


# def broken_task_function()  # <-- missing colon: this is a SyntaxError
#     print("This will never run")


# default_args = {
#     "owner": "data_platform_team",
#     "retries": 1,
# }

# with DAG(
#     dag_id="dag_broken_example",
#     default_args=default_args,
#     schedule_interval="@daily",
#     start_date=datetime(2024, 1, 1),
#     catchup=False,
# ) as dag:

#     broken_task = PythonOperator(
#         task_id="broken_task",
#         python_callable=broken_task_function,
#     )
