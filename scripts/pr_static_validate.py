"""
PR Static Validator
====================
Validates changed Python and SQL files in a Pull Request using static analysis.
No external runtime dependencies or Airflow installations are required.

Checks:
1. Python syntax compilation (compileall)
2. Airflow DAG structure and duplicate task validation (ast)
3. Hive SQL syntax validation (sqlfluff parse)

Usage:
    python scripts/pr_static_validate.py \
        --py-files "file1.py file2.py" \
        --sql-files "file1.sql file2.sql" \
        --summary-file "$GITHUB_STEP_SUMMARY"
"""

import argparse
import ast
import compileall
import os
import py_compile
import subprocess
import sys
from pathlib import Path


def parse_file_list(file_string: str) -> list[str]:
    """Parse a space-separated file string and return existing file paths."""
    if not file_string or not file_string.strip():
        return []
    files = [f.strip() for f in file_string.split() if f.strip()]
    return [f for f in files if Path(f).exists()]


# ---------------------------------------------------------------------------
# Check 1: Python Syntax (compileall)
# ---------------------------------------------------------------------------
def check_compileall(py_files: list[str]) -> dict[str, dict]:
    """Compile Python files to bytecode to verify syntax without executing code."""
    results = {}
    if not py_files:
        return results

    print("=" * 60)
    print("CHECK 1: Python Syntax Compilation (compileall)")
    print("=" * 60)

    for filepath in py_files:
        print(f"Compiling: {filepath}")

        success = compileall.compile_file(
            filepath,
            quiet=2,
            force=True,
        )

        if success:
            results[filepath] = {
                "status": "PASS",
                "details": "Syntax valid - compiled successfully",
            }
            print(f"  [PASS] {filepath}")
        else:
            try:
                py_compile.compile(filepath, doraise=True)
                results[filepath] = {"status": "PASS", "details": "Syntax valid"}
            except py_compile.PyCompileError as e:
                error_msg = str(e)[:200].replace("\n", " ").replace("|", "\\|")
                results[filepath] = {"status": "FAIL", "details": error_msg}
                print(f"  [FAIL] {filepath} - {error_msg}")

    return results


# ---------------------------------------------------------------------------
# Check 2: DAG Structure (AST - Abstract Syntax Tree)
# ---------------------------------------------------------------------------
def check_dag_structure(py_files: list[str]) -> dict[str, dict]:
    """Inspect Python AST to validate DAG structure and unique task IDs."""
    results = {}
    if not py_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 2: DAG Structure Validation (AST)")
    print("=" * 60)

    for filepath in py_files:
        print(f"Parsing AST: {filepath}")

        try:
            source_code = Path(filepath).read_text(encoding="utf-8")
        except Exception as e:
            error_msg = str(e)[:200].replace("\n", " ").replace("|", "\\|")
            results[filepath] = {
                "status": "FAIL",
                "details": f"Cannot read file: {error_msg}",
            }
            print(f"  [FAIL] {filepath} - Cannot read file")
            continue

        try:
            tree = ast.parse(source_code, filename=filepath)
        except SyntaxError as e:
            error_msg = f"Line {e.lineno}: {e.msg}"
            results[filepath] = {"status": "FAIL", "details": error_msg}
            print(f"  [FAIL] {filepath} - AST Parse Error: {error_msg}")
            continue

        dag_ids = []
        task_ids = []
        has_dag = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node)
                if func_name == "DAG":
                    has_dag = True
                    dag_id = _extract_dag_id(node)
                    if dag_id:
                        dag_ids.append(dag_id)

                task_id = _extract_task_id(node)
                if task_id:
                    task_ids.append(task_id)

        issues = []

        seen_dag_ids = set()
        for did in dag_ids:
            if did in seen_dag_ids:
                issues.append(f"Duplicate dag_id: '{did}'")
            seen_dag_ids.add(did)

        seen_task_ids = set()
        for tid in task_ids:
            if tid in seen_task_ids:
                issues.append(f"Duplicate task_id: '{tid}'")
            seen_task_ids.add(tid)

        if issues:
            detail = "; ".join(issues)
            results[filepath] = {"status": "FAIL", "details": detail}
            print(f"  [FAIL] {filepath} - {detail}")
        elif has_dag:
            dag_list = ", ".join(dag_ids) if dag_ids else "dag_id detected"
            task_count = len(task_ids)
            results[filepath] = {
                "status": "PASS",
                "details": f"DAG found ({dag_list}), {task_count} task(s) - structure valid",
            }
            print(f"  [PASS] {filepath} - DAG ({dag_list}), {task_count} task(s)")
        else:
            results[filepath] = {
                "status": "PASS",
                "details": "Non-DAG file - Python structure valid",
            }
            print(f"  [PASS] {filepath} - Non-DAG Python file")

    return results


def _get_call_name(node: ast.Call) -> str:
    """Return the function or method name from a Call AST node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _extract_dag_id(node: ast.Call) -> str:
    """Extract dag_id from positional or keyword arguments."""
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value

    for kw in node.keywords:
        if kw.arg == "dag_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value

    return ""


def _extract_task_id(node: ast.Call) -> str:
    """Extract task_id parameter from Operator Call nodes."""
    for kw in node.keywords:
        if kw.arg == "task_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return ""


# ---------------------------------------------------------------------------
# Check 3: Hive SQL Syntax (SQLFluff)
# ---------------------------------------------------------------------------
def check_sqlfluff(sql_files: list[str]) -> dict[str, dict]:
    """Validate SQL syntax against Hive dialect using SQLFluff parse."""
    results = {}
    if not sql_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 3: Hive SQL Syntax (SQLFluff)")
    print("=" * 60)

    for filepath in sql_files:
        print(f"Parsing: {filepath}")
        cmd = ["sqlfluff", "parse", "--dialect", "hive", filepath]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode == 0:
            results[filepath] = {"status": "PASS", "details": "No issues found"}
            print(f"  [PASS] {filepath}")
        else:
            error_output = (result.stdout or result.stderr or "Unknown error").strip()
            short_error = error_output[:200].replace("\n", " ").replace("|", "\\|")
            results[filepath] = {"status": "FAIL", "details": short_error}
            print(f"  [FAIL] {filepath} - {short_error}")

    return results


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------
def generate_report(
    compileall_results: dict,
    ast_results: dict,
    sqlfluff_results: dict,
    py_files: list[str],
    sql_files: list[str],
) -> tuple[str, bool]:
    """Generate Markdown summary report for GitHub Actions Step Summary."""
    lines = []
    all_passed = True

    lines.append("## PR Static Validation Report\n")

    if py_files:
        lines.append("### Python Files - Syntax Check (compileall)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in py_files:
            r = compileall_results.get(f, {"status": "SKIP", "details": "Not checked"})
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | **{r['status']}** | {r['details']} |")
        lines.append("")

    if py_files:
        lines.append("### Python Files - DAG Structure Validation (AST)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in py_files:
            r = ast_results.get(f, {"status": "SKIP", "details": "Not checked"})
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | **{r['status']}** | {r['details']} |")
        lines.append("")

    if sql_files:
        lines.append("### SQL Files - Syntax Check (SQLFluff Hive)\n")
        lines.append("| File | Status | Details |")
        lines.append("|:-----|:------:|:--------|")
        for f in sql_files:
            r = sqlfluff_results.get(f, {"status": "SKIP", "details": "Not checked"})
            if r["status"] == "FAIL":
                all_passed = False
            lines.append(f"| `{f}` | **{r['status']}** | {r['details']} |")
        lines.append("")

    if not py_files and not sql_files:
        lines.append("> No .py or .sql files were changed in this PR.\n")
        lines.append("### Result: SKIPPED (No relevant files to check)\n")
        return "\n".join(lines), True

    lines.append("---\n")
    if all_passed:
        lines.append("### Result: ALL CHECKS PASSED - Ready to Merge\n")
    else:
        lines.append("### Result: CHECKS FAILED - Please fix the errors above\n")

    return "\n".join(lines), all_passed


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Static validation of PR changed files")
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
    print("# PR Static Validator")
    print(f"# Python files: {len(py_files)}")
    print(f"# SQL files:    {len(sql_files)}")
    print("#" * 60)

    if not py_files and not sql_files:
        print("\nNo .py or .sql files changed in this PR. Validation skipped.\n")

    compileall_results = check_compileall(py_files)
    ast_results = check_dag_structure(py_files)
    sqlfluff_results = check_sqlfluff(sql_files)

    report, all_passed = generate_report(
        compileall_results, ast_results, sqlfluff_results, py_files, sql_files
    )

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(report)

    summary_path = args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(report)
        print(f"\nReport written to: {summary_path}")

    if all_passed:
        print("\nAll checks passed successfully.\n")
        sys.exit(0)
    else:
        print("\nOne or more checks failed. Review report above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
