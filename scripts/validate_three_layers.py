import compileall
import glob
import re
import subprocess
import sys
from pathlib import Path

from airflow.models import DagBag

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to skip during compileall and pylint scanning.
EXCLUDE_DIRS = [
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "airflow_home_ci",
    ".tox",
    "node_modules",
]

SEPARATOR = "=" * 60


# ---------------------------------------------------------------------------
# Layer 1 — Syntax check (compileall)
# ---------------------------------------------------------------------------
def check_syntax(repo_root: Path) -> bool:
    """Compile every .py file to bytecode without executing code.

    Catches: SyntaxError, IndentationError, invalid tokens.
    Does NOT execute any code — completely safe.
    """
    print(f"\n{SEPARATOR}")
    print("LAYER 1: Compile-check all Python files  (compileall)")
    print(SEPARATOR)

    exclude_pattern = re.compile(
        "|".join(rf"[/\\]{d}([/\\]|$)" for d in EXCLUDE_DIRS)
    )

    success = compileall.compile_dir(
        str(repo_root),
        maxlevels=50,
        quiet=1,      # quiet=1: only print errors
        rx=exclude_pattern,
        force=True,   # recompile even if .pyc is fresh
    )

    if success:
        print("\n  LAYER 1 PASSED — All Python files have valid syntax.\n")
    else:
        print("\n  LAYER 1 FAILED — Syntax errors found (see above).\n")

    return success


# ---------------------------------------------------------------------------
# Layer 2 — Static import check (pylint E0401)
# ---------------------------------------------------------------------------
def check_imports(repo_root: Path) -> bool:
    """Run pylint with only E0401 (import-error) enabled on every .py file.

    Catches: misspelled module/file names, missing third-party packages,
    missing __init__.py, wrong relative imports — all WITHOUT executing code.
    """
    print(f"\n{SEPARATOR}")
    print("LAYER 2: Static import check  (pylint E0401)")
    print(SEPARATOR)

    # Collect all .py files, excluding unwanted directories.
    py_files = []
    for filepath in sorted(glob.glob(str(repo_root / "**" / "*.py"), recursive=True)):
        if any(f"/{d}/" in filepath or filepath.endswith(f"/{d}") for d in EXCLUDE_DIRS):
            continue
        py_files.append(filepath)

    if not py_files:
        print("  No Python files found to check.")
        return True

    print(f"  Scanning {len(py_files)} Python file(s) for broken imports...\n")

    # Run pylint: disable everything except E0401 (import-error).
    cmd = [
        sys.executable, "-m", "pylint",
        "--disable=all",
        "--enable=E0401",
        "--output-format=text",
        "--score=no",
    ] + py_files

    result = subprocess.run(cmd, capture_output=True, text=True)

    # pylint exit codes are bitmasks:
    #   0 = no issues
    #   1 = fatal error (pylint itself crashed)
    #   2 = error messages were issued (E0401 hits)
    #   4 = warning, 8 = refactor, 16 = convention, 32 = usage error
    # We care about bit 1 (fatal) and bit 2 (error).

    stdout = result.stdout.strip()

    if stdout:
        print(stdout)
        print()

    has_errors = bool(result.returncode & 3)  # bits 0 (fatal) or 1 (error)

    if has_errors:
        print("  LAYER 2 FAILED — Broken imports found (see above).\n")
    else:
        print("  LAYER 2 PASSED — All imports resolved successfully.\n")

    return not has_errors


# ---------------------------------------------------------------------------
# Layer 3 — Airflow DAG validation (DagBag)
# ---------------------------------------------------------------------------
def check_dags(repo_root: Path) -> bool:
    """Load all DAGs via Airflow DagBag and check for import/parse errors.

    Catches: ImportError, ModuleNotFoundError, invalid DAG configuration,
    broken operators, circular imports — anything that fails at DAG load time.
    Note: This EXECUTES code (imports modules), so it catches runtime errors
    that static tools like pylint cannot detect.
    """
    print(f"\n{SEPARATOR}")
    print("LAYER 3: Airflow DAG validation  (DagBag)")
    print(SEPARATOR)
    print(f"  Scanning: {repo_root}\n")

    dagbag = DagBag(
        dag_folder=str(repo_root),
        include_examples=False,
        safe_mode=True,
    )

    if dagbag.import_errors:
        print(f"  Found {len(dagbag.import_errors)} DAG import error(s):\n")
        for filename, error in dagbag.import_errors.items():
            print(f"  --- {filename} ---")
            print(f"  {error}")
            print()
        print("  LAYER 3 FAILED — DAG import errors found.\n")
        return False

    dag_count = len(dagbag.dags)
    if dag_count == 0:
        print("  Warning: No DAGs were found. Verify your DAG files.\n")
    else:
        print(f"  Successfully validated {dag_count} DAG(s):")
        for dag_id in sorted(dagbag.dags):
            dag = dagbag.dags[dag_id]
            print(f"     - {dag_id}  (file: {dag.fileloc})")
        print()

    print("  LAYER 3 PASSED — All DAGs loaded without errors.\n")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"\n{'#' * 60}")
    print("#  Full Repository Validation (3-Layer)")
    print(f"#  Repo root: {REPO_ROOT}")
    print(f"{'#' * 60}")

    # Run all three layers. We run all of them even if earlier ones fail,
    # so the developer sees every problem in a single CI run.
    layer1_ok = check_syntax(REPO_ROOT)
    layer2_ok = check_imports(REPO_ROOT)
    layer3_ok = check_dags(REPO_ROOT)

    # Final summary
    print(f"\n{SEPARATOR}")
    print("FINAL SUMMARY")
    print(SEPARATOR)
    print(f"  Layer 1 — Syntax (compileall)     : {'PASS' if layer1_ok else 'FAIL'}")
    print(f"  Layer 2 — Imports (pylint E0401)   : {'PASS' if layer2_ok else 'FAIL'}")
    print(f"  Layer 3 — DAGs (Airflow DagBag)    : {'PASS' if layer3_ok else 'FAIL'}")
    print(SEPARATOR)

    if layer1_ok and layer2_ok and layer3_ok:
        print("\n  All 3 layers passed. Repository is clean.\n")
        sys.exit(0)
    else:
        print("\n  One or more layers failed. See details above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
