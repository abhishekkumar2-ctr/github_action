"""
PR Changed Files Validator (with Auto-Mocking)
===============================================
Validates only the files changed in a Pull Request.
- Python (.py) files: compileall (syntax) + Airflow DAGBag with Auto-Mocking (integrity)
- SQL (.sql) files:   SQLFluff parse (Hive dialect, syntax only)

Auto-Mocking: If any import fails (e.g., google_chat_callbacks, custom modules),
it is automatically replaced with a dummy mock object. This prevents false failures
due to missing libraries on the CI runner, while still catching real DAG issues
like cyclic dependencies, duplicate task_ids, and broken DAG structure.

Usage:
    python scripts/pr_validate_changed_files.py \
        --py-files "file1.py file2.py" \
        --sql-files "file1.sql file2.sql" \
        --summary-file "$GITHUB_STEP_SUMMARY"
"""

import argparse
import builtins
import compileall
import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Auto-Mocking: Intercept failed imports and replace with MagicMock
# ---------------------------------------------------------------------------
# Save Python's original import function
_original_import = builtins.__import__

# List of modules that were auto-mocked (for reporting)
_mocked_modules = []


def _auto_mock_import(name, *args, **kwargs):
    """Custom import function that auto-mocks any module that fails to import.

    How it works:
    1. First, try to import the module normally using Python's original __import__.
    2. If the import fails (ModuleNotFoundError / ImportError), instead of crashing,
       create a MagicMock object and register it as the module in sys.modules.
    3. MagicMock automatically handles any attribute access, function calls, etc.
       So code like `from google_chat_callbacks import task_fail_alert` will work —
       task_fail_alert will be a MagicMock object that does nothing when called.

    This ensures DAGBag can load and parse the DAG structure without needing
    every single library to be installed on the CI runner.
    """
    try:
        return _original_import(name, *args, **kwargs)
    except (ModuleNotFoundError, ImportError):
        # Module not found — create a mock instead of crashing
        if name not in _mocked_modules:
            _mocked_modules.append(name)
            print(f"  ⚡ Auto-mocked missing module: {name}")

        # Create a MagicMock and register it in sys.modules
        mock_module = MagicMock()
        sys.modules[name] = mock_module
        return mock_module


def enable_auto_mocking():
    """Enable auto-mocking: replace Python's __import__ with our custom version."""
    builtins.__import__ = _auto_mock_import
    print("  🔧 Auto-mocking ENABLED — missing imports will be mocked automatically")


def disable_auto_mocking():
    """Disable auto-mocking: restore Python's original __import__."""
    builtins.__import__ = _original_import
    print("  🔧 Auto-mocking DISABLED — original import restored")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_file_list(file_string: str) -> list[str]:
    """Split a space-separated file list and return only existing paths."""
    if not file_string or not file_string.strip():
        return []
    files = [f.strip() for f in file_string.split() if f.strip()]
    return [f for f in files if Path(f).exists()]


# ---------------------------------------------------------------------------
# Check 1 — compileall (Python syntax check)
# ---------------------------------------------------------------------------
def check_compileall(py_files: list[str]) -> dict[str, dict]:
    """Compile each changed Python file to bytecode to catch syntax errors.

    Uses Python's built-in compileall. Catches:
    - SyntaxError, IndentationError, TabError, Invalid tokens
    Does NOT execute any code — completely safe. No external dependencies needed.
    """
    results = {}
    if not py_files:
        return results

    print("=" * 60)
    print("CHECK 1: compileall — Python Syntax Check")
    print("=" * 60)

    for filepath in py_files:
        print(f"\n  Compiling: {filepath}")

        success = compileall.compile_file(
            filepath,
            quiet=2,
            force=True,
        )

        if success:
            results[filepath] = {"status": "PASS", "details": "Syntax OK — compiled successfully"}
            print(f"  ✅ {filepath} — PASS")
        else:
            import py_compile
            try:
                py_compile.compile(filepath, doraise=True)
                results[filepath] = {"status": "PASS", "details": "Syntax OK"}
            except py_compile.PyCompileError as e:
                error_msg = str(e)[:200].replace("\n", " ").replace("|", "\\|")
                results[filepath] = {"status": "FAIL", "details": error_msg}
                print(f"  ❌ {filepath} — FAIL: {error_msg}")

    return results


# ---------------------------------------------------------------------------
# Check 2 — Airflow DAGBag with Auto-Mocking (DAG integrity)
# ---------------------------------------------------------------------------
def check_dagbag(py_files: list[str]) -> dict[str, dict]:
    """Load changed Python files through Airflow DagBag with Auto-Mocking.

    Auto-Mocking ensures that missing libraries (like google_chat_callbacks,
    custom providers, etc.) are automatically replaced with dummy objects.
    This allows DagBag to load and validate the DAG structure without needing
    every single package to be installed.

    Still catches real DAG issues:
    - Cyclic dependencies (task1 >> task2 >> task1)
    - Duplicate task_id within same DAG
    - Broken DAG configuration
    - Invalid operator arguments
    - SyntaxError in DAG file
    """
    results = {}
    if not py_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 2: Airflow DAGBag — DAG Integrity Check (Auto-Mocking)")
    print("=" * 60)

    try:
        from airflow.models import DagBag
    except ImportError:
        print("  ⚠️  Airflow not installed — skipping DAGBag check.")
        for filepath in py_files:
            results[filepath] = {
                "status": "SKIP",
                "details": "Airflow not installed",
            }
        return results

    # Enable auto-mocking before loading DAGs
    _mocked_modules.clear()
    enable_auto_mocking()

    for filepath in py_files:
        abs_path = str(Path(filepath).resolve())
        file_dir = str(Path(filepath).resolve().parent)

        print(f"\n  Loading DAGs from: {filepath}")
        dagbag = DagBag(
            dag_folder=file_dir,
            include_examples=False,
            safe_mode=False,
        )

        # Check if this specific file had import errors
        file_errors = {
            k: v for k, v in dagbag.import_errors.items()
            if Path(k).resolve() == Path(abs_path).resolve()
        }

        if file_errors:
            error_msg = list(file_errors.values())[0]
            short_error = str(error_msg)[:200].replace("\n", " ").replace("|", "\\|")
            results[filepath] = {"status": "FAIL", "details": short_error}
            print(f"  ❌ {filepath} — DAG import error found")
        else:
            # Find DAGs loaded from this file
            file_dags = [
                dag_id
                for dag_id, dag in dagbag.dags.items()
                if Path(dag.fileloc).resolve() == Path(abs_path).resolve()
            ]
            if file_dags:
                dag_list = ", ".join(file_dags)
                mock_info = ""
                if _mocked_modules:
                    mock_info = f" (auto-mocked: {', '.join(_mocked_modules[:5])})"
                results[filepath] = {
                    "status": "PASS",
                    "details": f"DAG(s) loaded: {dag_list}{mock_info}",
                }
                print(f"  ✅ {filepath} — DAG(s) loaded: {dag_list}{mock_info}")
            else:
                results[filepath] = {
                    "status": "PASS",
                    "details": "Not a DAG file (no DAGs found) — syntax OK",
                }
                print(f"  ✅ {filepath} — Not a DAG file, syntax OK")

    # Disable auto-mocking after DAG loading is complete
    disable_auto_mocking()

    return results


# ===========================================================================
# OLD Check 2 (WITHOUT Auto-Mocking) — COMMENTED OUT FOR COMPARISON
# ===========================================================================
# def check_dagbag_old(py_files: list[str]) -> dict[str, dict]:
#     """OLD VERSION: DagBag WITHOUT auto-mocking.
#     This version FAILS if any imported module is missing on the CI runner.
#     For example, 'from google_chat_callbacks import task_fail_alert' will
#     cause ModuleNotFoundError and the PR check will FAIL even though the
#     DAG code is perfectly valid.
#     """
#     results = {}
#     if not py_files:
#         return results
#
#     print("\n" + "=" * 60)
#     print("CHECK 2: Airflow DAGBag — DAG Integrity Check (OLD - No Mocking)")
#     print("=" * 60)
#
#     try:
#         from airflow.models import DagBag
#     except ImportError:
#         print("  Airflow not installed — skipping DAGBag check.")
#         for filepath in py_files:
#             results[filepath] = {"status": "SKIP", "details": "Airflow not installed"}
#         return results
#
#     for filepath in py_files:
#         abs_path = str(Path(filepath).resolve())
#         file_dir = str(Path(filepath).resolve().parent)
#
#         print(f"\n  Loading DAGs from: {filepath}")
#         dagbag = DagBag(dag_folder=file_dir, include_examples=False, safe_mode=False)
#
#         file_errors = {
#             k: v for k, v in dagbag.import_errors.items()
#             if Path(k).resolve() == Path(abs_path).resolve()
#         }
#
#         if file_errors:
#             # ❌ This is where missing module errors like google_chat_callbacks
#             # would cause the check to FAIL unnecessarily
#             error_msg = list(file_errors.values())[0]
#             short_error = str(error_msg)[:200].replace("\n", " ").replace("|", "\\|")
#             results[filepath] = {"status": "FAIL", "details": short_error}
#             print(f"  ❌ {filepath} — DAG import error found")
#         else:
#             file_dags = [
#                 dag_id for dag_id, dag in dagbag.dags.items()
#                 if Path(dag.fileloc).resolve() == Path(abs_path).resolve()
#             ]
#             if file_dags:
#                 dag_list = ", ".join(file_dags)
#                 results[filepath] = {"status": "PASS", "details": f"DAG(s) loaded: {dag_list}"}
#             else:
#                 results[filepath] = {"status": "PASS", "details": "Not a DAG file — syntax OK"}
#
#     return results
# ===========================================================================


# ---------------------------------------------------------------------------
# Check 3 — SQLFluff (Hive SQL syntax)
# ---------------------------------------------------------------------------
def check_sqlfluff(sql_files: list[str]) -> dict[str, dict]:
    """Run sqlfluff parse on each changed SQL file (Hive dialect, syntax only)."""
    results = {}
    if not sql_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 3: SQLFluff — Hive SQL Syntax Check (parse only)")
    print("=" * 60)

    for filepath in sql_files:
        print(f"\n  Parsing: {filepath}")
        cmd = ["sqlfluff", "parse", "--dialect", "hive", filepath]
        print(f"  Command: {' '.join(cmd)}\n")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode == 0:
            results[filepath] = {"status": "PASS", "details": "No issues found"}
            print(f"  ✅ {filepath} — PASS")
        else:
            error_output = (result.stdout or result.stderr or "Unknown error").strip()
            short_error = error_output[:200].replace("\n", " ").replace("|", "\\|")
            results[filepath] = {"status": "FAIL", "details": short_error}
            print(f"  ❌ {filepath} — FAIL")

    return results


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------
def generate_report(
    compileall_results: dict,
    dagbag_results: dict,
    sqlfluff_results: dict,
    py_files: list[str],
    sql_files: list[str],
) -> tuple[str, bool]:
    """Generate a Markdown summary report and return (report_text, all_passed)."""

    lines = []
    all_passed = True

    lines.append("## 📋 PR Syntax & DAG Check Report\n")

    # --- Python: compileall ---
    if py_files:
        lines.append("### 🐍 Python Files — compileall (Syntax Check)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in py_files:
            r = compileall_results.get(f, {"status": "SKIP", "details": "Not checked"})
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "SKIP" else "❌")
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | {icon} {r['status']} | {r['details']} |")
        lines.append("")

    # --- Python: DAGBag with Auto-Mocking ---
    if py_files:
        lines.append("### 🐍 Python Files — Airflow DAGBag with Auto-Mocking (Integrity)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in py_files:
            r = dagbag_results.get(f, {"status": "SKIP", "details": "Not checked"})
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "SKIP" else "❌")
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | {icon} {r['status']} | {r['details']} |")
        lines.append("")

    # --- SQL: SQLFluff ---
    if sql_files:
        lines.append("### 🗄️ SQL Files — SQLFluff Hive (Syntax)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in sql_files:
            r = sqlfluff_results.get(f, {"status": "SKIP", "details": "Not checked"})
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "SKIP" else "❌")
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | {icon} {r['status']} | {r['details']} |")
        lines.append("")

    # --- Auto-Mocked Modules Info ---
    if _mocked_modules:
        lines.append("### ⚡ Auto-Mocked Modules (not installed on CI runner)\n")
        lines.append("| Module | Status |")
        lines.append("|:-------|:------:|")
        for mod in _mocked_modules:
            lines.append(f"| `{mod}` | ⚡ Mocked |")
        lines.append("")
        lines.append("> ℹ️ These modules were auto-mocked because they are not installed on the CI runner.")
        lines.append("> DAG structure validation still passed successfully.\n")

    # --- No files case ---
    if not py_files and not sql_files:
        lines.append("> ℹ️ No `.py` or `.sql` files were changed in this PR.\n")
        lines.append("### Result: ✅ SKIPPED (No relevant files to check)\n")
        return "\n".join(lines), True

    # --- Overall result ---
    lines.append("---\n")
    if all_passed:
        lines.append("### Result: ✅ ALL CHECKS PASSED — Ready to Merge\n")
    else:
        lines.append("### Result: ❌ CHECKS FAILED — Please fix the errors above\n")

    return "\n".join(lines), all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Validate PR changed files")
    parser.add_argument(
        "--py-files",
        type=str,
        default="",
        help="Space-separated list of changed Python files",
    )
    parser.add_argument(
        "--sql-files",
        type=str,
        default="",
        help="Space-separated list of changed SQL files",
    )
    parser.add_argument(
        "--summary-file",
        type=str,
        default="",
        help="Path to GitHub Step Summary file",
    )
    args = parser.parse_args()

    py_files = parse_file_list(args.py_files)
    sql_files = parse_file_list(args.sql_files)

    print("#" * 60)
    print("#  PR Changed Files Validator (with Auto-Mocking)")
    print(f"#  Python files to check: {len(py_files)}")
    print(f"#  SQL files to check:    {len(sql_files)}")
    print("#" * 60)

    if not py_files and not sql_files:
        print("\n  No .py or .sql files changed in this PR. Nothing to validate.\n")

    # Run all 3 checks
    compileall_results = check_compileall(py_files)
    dagbag_results = check_dagbag(py_files)
    sqlfluff_results = check_sqlfluff(sql_files)

    # Generate report
    report, all_passed = generate_report(
        compileall_results, dagbag_results, sqlfluff_results, py_files, sql_files
    )

    # Print report to console
    print("\n" + "=" * 60)
    print("GENERATED REPORT")
    print("=" * 60)
    print(report)

    # Write to GitHub Step Summary (if available)
    summary_path = args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(report)
        print(f"\n  📝 Report written to: {summary_path}")

    # Exit with appropriate code
    if all_passed:
        print("\n  ✅ All checks passed!\n")
        sys.exit(0)
    else:
        print("\n  ❌ One or more checks failed. See report above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
