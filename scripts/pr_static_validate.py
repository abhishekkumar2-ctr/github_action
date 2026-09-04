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

        # Check for duplicate dag_id in same file
        seen_dag_ids = set()
        for did in dag_ids:
            if did in seen_dag_ids:
                issues.append(f"Duplicate dag_id: '{did}'")
            seen_dag_ids.add(did)

        # Check for duplicate task_id in same file
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
# Check 3: Multi-Dialect SQL Syntax (SQLFluff - Hive, Trino, MySQL)
# ---------------------------------------------------------------------------
SQL_DIALECTS = ["hive", "trino", "mysql"]


def _extract_sqlfluff_error(output: str) -> str:
    """Extract clean error message from SQLFluff output, skipping parse tree dumps."""
    if not output:
        return "Unknown SQL parsing error"

    lines = output.splitlines()
    violations = []
    in_violations = False

    for line in lines:
        if "parsing violations" in line.lower():
            in_violations = True
            continue
        if in_violations:
            if line.startswith("WARNING:") or (line.startswith("===") and in_violations):
                break
            line_str = line.strip()
            if line_str and ("Line " in line_str or "PRS" in line_str or "Found unparsable" in line_str):
                clean_line = " ".join(line_str.split()).replace("|", " ")
                violations.append(clean_line)

    if violations:
        return " ; ".join(violations[:2])

    for line in reversed(lines):
        if "Line " in line or "Found unparsable" in line or "FAIL" in line:
            return " ".join(line.strip().split()).replace("|", " ")[:200]

    return "SQL syntax error found"


def _run_sqlfluff_parse(filepath: str, dialect: str) -> dict:
    """Run sqlfluff parse for a specific dialect and return result dict."""
    cmd = ["sqlfluff", "parse", "--dialect", dialect, filepath]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return {"status": "PASS", "error": ""}
    else:
        raw_output = (result.stdout or result.stderr or "Unknown error").strip()
        clean_error = _extract_sqlfluff_error(raw_output)
        return {"status": "FAIL", "error": clean_error}


def check_sqlfluff_multi_dialect(sql_files: list[str]) -> dict[str, dict]:
    """Test each SQL file against Hive, Trino, and MySQL dialects.

    Decision rule:
    - PASS if the file is valid in at least one dialect
    - FAIL only if the file is invalid in ALL three dialects
    """
    results = {}
    if not sql_files:
        return results

    print("\n" + "=" * 60)
    print("CHECK 3: Multi-Dialect SQL Syntax (Hive, Trino, MySQL)")
    print("=" * 60)

    for filepath in sql_files:
        print(f"\nValidating: {filepath}")
        dialect_results = {}
        passed_dialects = []

        for dialect in SQL_DIALECTS:
            dr = _run_sqlfluff_parse(filepath, dialect)
            dialect_results[dialect] = dr

            if dr["status"] == "PASS":
                passed_dialects.append(dialect.upper())
                print(f"  - Testing {dialect.upper():8s}: PASS (Syntax valid)")
            else:
                print(f"  - Testing {dialect.upper():8s}: FAIL ({dr['error']})")

        if passed_dialects:
            matched_str = ", ".join(passed_dialects)
            print(f"  -> Final Result: [PASS] (Matched {matched_str} SQL)")
            results[filepath] = {
                "status": "PASS",
                "matched": matched_str,
                "dialect_results": dialect_results,
                "details": f"Syntax valid - matched {matched_str}",
            }
        else:
            error_parts = []
            for d in SQL_DIALECTS:
                err = dialect_results[d]["error"]
                error_parts.append(f"{d.upper()}: {err}")
            combined_error = " | ".join(error_parts)
            short_error = combined_error[:300]

            print(f"  -> Final Result: [FAIL] (Failed in all 3 dialects)")
            results[filepath] = {
                "status": "FAIL",
                "matched": "NONE",
                "dialect_results": dialect_results,
                "details": f"Failed in all dialects - {short_error}",
            }

    return results


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------
def generate_report(
    compileall_results: dict,
    ast_results: dict,
    sql_results: dict,
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
        lines.append("### SQL Files - Multi-Dialect Syntax Check (Hive / Trino / MySQL)\n")
        lines.append("| File | Result | Hive | Trino | MySQL | Details |")
        lines.append("|:-----|:------:|:----:|:-----:|:-----:|:--------|")
        for f in sql_files:
            r = sql_results.get(f, {
                "status": "SKIP",
                "matched": "-",
                "dialect_results": {},
                "details": "Not checked",
            })
            if r["status"] == "FAIL":
                all_passed = False

            dr = r.get("dialect_results", {})
            hive_st = dr.get("hive", {}).get("status", "-")
            trino_st = dr.get("trino", {}).get("status", "-")
            mysql_st = dr.get("mysql", {}).get("status", "-")

            lines.append(
                f"| `{f}` | **{r['status']}** | {hive_st} | {trino_st} | {mysql_st} | {r['details']} |"
            )

        failed_sql = [f for f in sql_files if sql_results.get(f, {}).get("status") == "FAIL"]
        if failed_sql:
            lines.append("")
            lines.append("**Failure Details (per dialect):**\n")
            for f in failed_sql:
                r = sql_results[f]
                dr = r.get("dialect_results", {})
                lines.append(f"**`{f}`**:")
                for d in SQL_DIALECTS:
                    err = dr.get(d, {}).get("error", "N/A")
                    lines.append(f"- {d.upper()}: {err}")
                lines.append("")

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
    print("# PR Static Validator (Multi-Dialect SQL)")
    print(f"# Python files: {len(py_files)}")
    print(f"# SQL files:    {len(sql_files)}")
    print("#" * 60)

    if not py_files and not sql_files:
        print("\nNo .py or .sql files changed in this PR. Validation skipped.\n")

    compileall_results = check_compileall(py_files)
    ast_results = check_dag_structure(py_files)
    sql_results = check_sqlfluff_multi_dialect(sql_files)

    report, all_passed = generate_report(
        compileall_results, ast_results, sql_results, py_files, sql_files
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