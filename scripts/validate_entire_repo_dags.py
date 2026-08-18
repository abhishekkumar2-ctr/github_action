import sys
from pathlib import Path

from airflow.models import DagBag

REPO_ROOT = Path(__file__).resolve().parent.parent


def validate_dags(dag_folder: str = str(REPO_ROOT)) -> None:
    print(f"Scanning entire repository for DAGs from: {dag_folder}\n")
    print("(folders listed in .airflowignore will be skipped)\n")

    dagbag = DagBag(dag_folder=dag_folder, include_examples=False, safe_mode=True)

    if dagbag.import_errors:
        print(f"Found {len(dagbag.import_errors)} DAG import error(s):\n")
        for filename, error in dagbag.import_errors.items():
            print(f"--- {filename} ---")
            print(error)
            print()
        sys.exit(1)

    if len(dagbag.dags) == 0:
        print("Warning: No DAGs were found anywhere in the repo. Check your files.")

    print(f"Successfully validated {len(dagbag.dags)} DAG(s) across the repo:")
    for dag_id in sorted(dagbag.dags):
        dag = dagbag.dags[dag_id]
        print(f"   - {dag_id}  (file: {dag.fileloc})")

    sys.exit(0)


if __name__ == "__main__":
    validate_dags()