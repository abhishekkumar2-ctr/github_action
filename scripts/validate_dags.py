"""
validate_dags.py

Loads every DAG file under airflow_home/dags/ via Airflow's DagBag,
which catches:
  - Python syntax errors
  - Import errors (missing modules, typos, etc.)
  - Airflow-specific DAG integrity errors (duplicate dag_id, cycles,
    bad default_args, etc.)

Exits with code 1 if any import errors are found (fails the CI job).
Exits with code 0 if all DAGs load cleanly.
"""
import sys

from airflow.models import DagBag

DAG_FOLDER = "airflow_home/dags"


def validate_dags(dag_folder: str = DAG_FOLDER) -> None:
    print(f"Loading DAGs from: {dag_folder}\n")

    dagbag = DagBag(dag_folder=dag_folder, include_examples=False)

    if dagbag.import_errors:
        print(f"❌ Found {len(dagbag.import_errors)} DAG import error(s):\n")
        for filename, error in dagbag.import_errors.items():
            print(f"--- {filename} ---")
            print(error)
            print()
        sys.exit(1)

    if len(dagbag.dags) == 0:
        print("⚠️  Warning: No DAGs were found. Check your dag_folder path.")

    print(f"✅ Successfully validated {len(dagbag.dags)} DAG(s):")
    for dag_id in sorted(dagbag.dags):
        print(f"   - {dag_id}")

    sys.exit(0)


if __name__ == "__main__":
    validate_dags()
