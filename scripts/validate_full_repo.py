import compileall
import sys
from pathlib import Path

from airflow.models import DagBag

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories that should be excluded from compile-all scanning.
COMPILE_EXCLUDE_DIRS = [
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "airflow_home_ci",
    ".tox",
    "node_modules",
]


def check_syntax(repo_root: Path) -> bool:
    """Compile every .py file under *repo_root* and return True if all pass."""
    print("=" * 60)
    print("STEP 1: Compile-check all Python files")
    print("=" * 60)

    # Build a regex pattern for directories to skip.
    # compileall.compile_dir `rx` param matches against the full path.
    import re

    exclude_pattern = re.compile(
        "|".join(rf"[/\\]{d}([/\\]|$)" for d in COMPILE_EXCLUDE_DIRS)
    )

    success = compileall.compile_dir(
        str(repo_root),
        maxlevels=50,
        quiet=1,        # quiet=1: only print errors
        rx=exclude_pattern,
        force=True,     # recompile even if .pyc is fresh
    )

    if success:
        print("\n All Python files compiled successfully.\n")
    else:
        print("\n Syntax / compilation errors found (see above).\n")

    return success


def check_dags(repo_root: Path) -> bool:
    """Load DAGs from *repo_root* via DagBag and return True if no errors."""
    print("=" * 60)
    print("STEP 2: Validate Airflow DAGs (DagBag import check)")
    print("=" * 60)
    print(f"Scanning: {repo_root}\n")

    dagbag = DagBag(
        dag_folder=str(repo_root),
        include_examples=False,
        safe_mode=True,
    )

    if dagbag.import_errors:
        print(f"Found {len(dagbag.import_errors)} DAG import error(s):\n")
        for filename, error in dagbag.import_errors.items():
            print(f"--- {filename} ---")
            print(error)
            print()
        return False

    dag_count = len(dagbag.dags)
    if dag_count == 0:
        print("Warning: No DAGs were found. Verify your DAG files.\n")
    else:
        print(f"Successfully validated {dag_count} DAG(s):")
        for dag_id in sorted(dagbag.dags):
            dag = dagbag.dags[dag_id]
            print(f"   • {dag_id}  (file: {dag.fileloc})")
        print()

    return True


def main() -> None:
    print(f"\n{'#' * 60}")
    print("#  Full Repository Validation")
    print(f"#  Repo root: {REPO_ROOT}")
    print(f"{'#' * 60}\n")

    syntax_ok = check_syntax(REPO_ROOT)
    dags_ok = check_dags(REPO_ROOT)

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Syntax / Compilation : {'PASS ' if syntax_ok else 'FAIL '}")
    print(f"  Airflow DAG Import   : {'PASS ' if dags_ok else 'FAIL '}")
    print("=" * 60)

    if syntax_ok and dags_ok:
        print("\n All validations passed.\n")
        sys.exit(0)
    else:
        print("\n One or more validations failed. See details above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
