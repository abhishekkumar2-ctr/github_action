import argparse
import compileall
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    results = {}
    if not py_files:
        return results

    print("=" * 60)
    print("CHECK 1: compileall — Python Syntax Check")
    print("=" * 60)

    for filepath in py_files:
        print(f"\n  Compiling: {filepath}")

        # compileall.compile_file returns True if compilation succeeds
        success = compileall.compile_file(
            filepath,
            quiet=2,    # quiet=2: suppress all output (we handle it ourselves)
            force=True,  # recompile even if .pyc is fresh
        )

        if success:
            results[filepath] = {"status": "PASS", "details": "Syntax OK — compiled successfully"}
            print(f" {filepath} — PASS")
        else:
            # To capture the actual error message, use py_compile
            import py_compile
            try:
                py_compile.compile(filepath, doraise=True)
                # If we get here, it somehow passed (shouldn't happen)
                results[filepath] = {"status": "PASS", "details": "Syntax OK"}
            except py_compile.PyCompileError as e:
                error_msg = str(e)[:200].replace("\n", " ").replace("|", "\\|")
                results[filepath] = {"status": "FAIL", "details": error_msg}
                print(f" {filepath} — FAIL: {error_msg}")

    return results


# ---------------------------------------------------------------------------
# Check 2 — Airflow DAGBag (DAG integrity)
# ---------------------------------------------------------------------------
def check_dagbag(py_files: list[str]) -> dict[str, dict]:
    results = {}
    if not py_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 2: Airflow DAGBag — DAG Integrity Check")
    print("=" * 60)

    try:
        from airflow.models import DagBag
    except ImportError:
        print(" Airflow not installed — skipping DAGBag check.")
        for filepath in py_files:
            results[filepath] = {
                "status": "SKIP",
                "details": "Airflow not installed",
            }
        return results

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
            print(f" {filepath} — DAG import error found")
        else:
            # Find DAGs loaded from this file
            file_dags = [
                dag_id
                for dag_id, dag in dagbag.dags.items()
                if Path(dag.fileloc).resolve() == Path(abs_path).resolve()
            ]
            if file_dags:
                dag_list = ", ".join(file_dags)
                results[filepath] = {
                    "status": "PASS",
                    "details": f"DAG(s) loaded: {dag_list}",
                }
                print(f" {filepath} — DAG(s) loaded: {dag_list}")
            else:
                results[filepath] = {
                    "status": "PASS",
                    "details": "Not a DAG file (no DAGs found) — syntax OK",
                }
                print(f" {filepath} — Not a DAG file, syntax OK")

    return results


# ---------------------------------------------------------------------------
# Check 3 — SQLFluff (Hive SQL syntax)
# ---------------------------------------------------------------------------
def check_sqlfluff(sql_files: list[str]) -> dict[str, dict]:
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
            print(f" {filepath} — PASS")
        else:
            error_output = (result.stdout or result.stderr or "Unknown error").strip()
            short_error = error_output[:200].replace("\n", " ").replace("|", "\\|")
            results[filepath] = {"status": "FAIL", "details": short_error}
            print(f" {filepath} — FAIL")

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

    lines.append("## PR Syntax & DAG Check Report\n")

    # --- Python: compileall ---
    if py_files:
        lines.append("### Python Files — compileall (Syntax Check)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in py_files:
            r = compileall_results.get(f, {"status": "SKIP", "details": "Not checked"})
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "SKIP" else "❌")
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | {icon} {r['status']} | {r['details']} |")
        lines.append("")

    # --- Python: DAGBag ---
    if py_files:
        lines.append("### Python Files — Airflow DAGBag (Integrity)\n")
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
        lines.append("### SQL Files — SQLFluff Hive (Syntax)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in sql_files:
            r = sqlfluff_results.get(f, {"status": "SKIP", "details": "Not checked"})
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "SKIP" else "❌")
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | {icon} {r['status']} | {r['details']} |")
        lines.append("")

    # --- No files case ---
    if not py_files and not sql_files:
        lines.append("> No `.py` or `.sql` files were changed in this PR.\n")
        lines.append("### Result: SKIPPED (No relevant files to check)\n")
        return "\n".join(lines), True

    # --- Overall result ---
    lines.append("---\n")
    if all_passed:
        lines.append("### Result: ALL CHECKS PASSED — Ready to Merge\n")
    else:
        lines.append("### Result: CHECKS FAILED — Please fix the errors above\n")

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
    print("#  PR Changed Files Validator")
    print(f"#  Python files to check: {len(py_files)}")
    print(f"#  SQL files to check:    {len(sql_files)}")
    print("#" * 60)

    if not py_files and not sql_files:
        print("\n  No .py or .sql files changed in this PR. Nothing to validate.\n")

    # Run all 3 checks (run all even if earlier ones fail, so developer sees all errors)
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
        print(f"\n Report written to: {summary_path}")

    # Exit with appropriate code
    if all_passed:
        print("\n  All checks passed!\n")
        sys.exit(0)
    else:
        print("\n One or more checks failed. See report above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
