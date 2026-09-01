import os
import sys
AIRFLOW_HOME = os.environ.get('ANALYTICS_AIRFLOW_HOME')
import pendulum
from datetime import datetime, timedelta, time, date
from airflow.operators.python import PythonOperator
from airflow import DAG
from airflow.operators.dummy import DummyOperator
# from google_chat_callbacks import task_fail_alert, task_success_alert
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor as GoogleCloudStorageObjectSensor
from airflow.operators.bash_operator import BashOperator
ENVR = 'PROD'

sys.path.insert(1, os.path.join(os.environ.get('ANALYTICS_AIRFLOW_HOME', ''), "scripts/aknamed/sales/control_tower/python/"))
from control_tower_mtd_prev_day_mail import email_sent as control_tower_mail

dag_params = {
    'start_date': pendulum.datetime(2024, 3, 21, tz="Asia/Kolkata"),
    # 'on_failure_callback': task_fail_alert if ENVR == 'PROD' else None,
    # 'on_success_callback': task_success_alert if ENVR == 'PROD' else None,
    'retries': 5,
    'owner': 'bhuvan.ram@pharmeasy.in',
    'retry_delay': timedelta(minutes=5),
    'catchup': False
}

def pe_s3_sensor(dag_name, task_name, dag,**kwargs):
    
    bucket_loc = "analytics/pe/s3_sensor/" + dag_name + "/" + task_name + "/"

    today = datetime.now() + timedelta(minutes = 330) 
    file_name = task_name + "_" + today.strftime("%Y_%m_%d")+".txt"
    
    pe_s3_task = GoogleCloudStorageObjectSensor(
        task_id = 'gcs_task'+"_" + task_name,
        object = bucket_loc + file_name , bucket="pe-skull-external-data",
        google_cloud_conn_id = "google_cloud_default", dag = dag,
        timeout=60*2,  
        mode="reschedule",
        poke_interval=60*1,  
    )
    
    return pe_s3_task

with DAG('akna_control_tower',
         default_args=dag_params,
         description='akna_control_tower',
         schedule_interval='0 12 * * *', 
         tags=['aknamed','sales','P0']) as dag:

    start_operator = DummyOperator(task_id='start')
    end_operator = DummyOperator(task_id='end')
    
    task = PythonOperator(
    task_id='control_tower_mail',
    python_callable=control_tower_mail,
    dag=dag,execution_timeout=timedelta(minutes=20)
    )
             
    aknamed_sales_sensor = pe_s3_sensor(dag_name="proc_ops_aknamed_fill_rate",task_name="aknamed_sales",dag=dag)
    # define and add control query task below 
    start_operator >> aknamed_sales_sensor >> task >> end_operator
  