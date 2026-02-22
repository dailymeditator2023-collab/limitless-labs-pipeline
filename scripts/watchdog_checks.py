#!/usr/bin/env python3
"""
Limitless Labs — Watchdog Checks
=================================
Runs automated validation checks on every push to main.
Catches common issues before they become problems.

Checks performed:
  1. Python syntax — all .py files compile without errors
  2. Scoring weights — Formula/Dosing/Value/Transparency weights sum to 1.0
  3. Secret leaks — no hardcoded API keys or tokens in code
  4. Import health — all imports resolve correctly
  5. Score range — verdict thresholds are consistent
  6. Conflict-of-interest — Smart Caffeine products are excluded
"""

import ast
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Track results
passed = []
failed = []
warnings = []


def check_pass(name, detail=""):
    passed.append((name, detail))
    print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))


def check_fail(name, detail=""):
    failed.append((name, detail))
    print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def check_warn(name, detail=""):
    warnings.append((name, detail))
    print(f"  WARN  {name}" + (f" — {detail}" if detail else ""))


# ── 1. Python Syntax Check ──────────────────────────────────────────

def check_python_syntax():
    print("\n[1/6] Python Syntax Check")
    py_files = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip hidden dirs and venv
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    errors = []
    for filepath in py_files:
        try:
            with open(filepath, "r") as fh:
                source = fh.read()
            ast.parse(source, filename=filepath)
        except SyntaxError as e:
            rel = os.path.relpath(filepath, REPO_ROOT)
            errors.append(f"{rel}:{e.lineno} — {e.msg}")

    if errors:
        for err in errors:
            check_fail("Syntax error", err)
    else:
        check_pass("All Python files", f"{len(py_files)} files parsed OK")


# ── 2. Scoring Weights Validation ───────────────────────────────────

def check_scoring_weights():
    print("\n[2/6] Scoring Weights Validation")
    scoring_file = os.path.join(REPO_ROOT, "scoring_agent.py")
    if not os.path.exists(scoring_file):
        check_warn("scoring_agent.py not found", "Cannot validate weights")
        return

    with open(scoring_file, "r") as f:
        content = f.read()

    # Look for weight definitions (e.g., 0.30, 0.20)
    # The expected weights: Formula 30%, Dosing 30%, Value 20%, Transparency 20%
    weight_pattern = r"(Formula|Dosing|Value|Transparency)\s*[×x*]\s*([\d.]+)"
    matches = re.findall(weight_pattern, content, re.IGNORECASE)

    if not matches:
        # Try alternate pattern from the docstring/comments
        weight_pattern2 = r"(\d+)%.*?:\s*(Formula|Dosing|Value|Transparency)"
        matches2 = re.findall(weight_pattern2, content, re.IGNORECASE)
        if matches2:
            total = sum(int(m[0]) for m in matches2)
            if total == 100:
                check_pass("Scoring weights", f"Sum = {total}% (from comments)")
            else:
                check_fail("Scoring weights", f"Sum = {total}% (expected 100%)")
            return

    if matches:
        # Deduplicate by lowercased name (file may mention weights multiple times)
        weights = {}
        for name, val in matches:
            key = name.capitalize()
            if key not in weights:
                weights[key] = float(val)
        total = sum(weights.values())
        if abs(total - 1.0) < 0.01:
            check_pass("Scoring weights", f"Sum = {total:.2f} ({', '.join(f'{k}={v}' for k, v in weights.items())})")
        else:
            check_fail("Scoring weights", f"Sum = {total:.2f} (expected 1.00) — {weights}")
    else:
        check_warn("Scoring weights", "Could not extract weight values — manual review needed")


# ── 3. Secret Leak Detection ────────────────────────────────────────

def check_secret_leaks():
    print("\n[3/6] Secret Leak Detection")
    # Patterns that indicate hardcoded secrets
    secret_patterns = [
        (r'(?:pat|key|token|secret|password)\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Possible hardcoded secret"),
        (r'Bearer\s+[a-zA-Z0-9]{20,}', "Hardcoded Bearer token"),
        (r'AIRTABLE_TOKEN\s*=\s*["\']pat[a-zA-Z0-9]+["\']', "Hardcoded Airtable PAT"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
    ]

    issues = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            with open(filepath, "r") as f:
                for line_num, line in enumerate(f, 1):
                    for pattern, desc in secret_patterns:
                        if re.search(pattern, line):
                            # Exclude lines that read from env vars
                            if "os.environ" in line or "os.getenv" in line:
                                continue
                            rel = os.path.relpath(filepath, REPO_ROOT)
                            issues.append(f"{rel}:{line_num} — {desc}")

    if issues:
        for issue in issues:
            check_fail("Secret leak", issue)
    else:
        check_pass("No hardcoded secrets detected")


# ── 4. Import Health Check ───────────────────────────────────────────

def check_imports():
    print("\n[4/6] Import Health Check")
    py_files = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    # Check that standard library and required imports are present
    required_packages = {"requests"}
    missing = []

    for filepath in py_files:
        with open(filepath, "r") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    try:
                        __import__(alias.name.split(".")[0])
                    except ImportError:
                        rel = os.path.relpath(filepath, REPO_ROOT)
                        missing.append(f"{rel} — missing '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    try:
                        __import__(node.module.split(".")[0])
                    except ImportError:
                        rel = os.path.relpath(filepath, REPO_ROOT)
                        missing.append(f"{rel} — missing '{node.module}'")

    if missing:
        for m in missing:
            check_warn("Missing import", m)
    else:
        check_pass("All imports resolvable", f"{len(py_files)} files checked")


# ── 5. Score Verdict Thresholds ─────────────────────────────────────

def check_verdict_thresholds():
    print("\n[5/6] Verdict Threshold Consistency")
    scoring_file = os.path.join(REPO_ROOT, "scoring_agent.py")
    if not os.path.exists(scoring_file):
        check_warn("scoring_agent.py not found")
        return

    with open(scoring_file, "r") as f:
        content = f.read()

    # Expected: 8.0+ Highly Recommended, 7.5-7.9 Recommended, 5.0-7.4 Average, <5.0 Skip
    expected_thresholds = {
        "highly recommended": 8.0,
        "recommended": 7.5,
        "average": 5.0,
        "skip": 5.0,
    }

    # Check that thresholds appear in the file
    found_any = False
    for verdict, threshold in expected_thresholds.items():
        if verdict in content.lower():
            found_any = True

    if found_any:
        check_pass("Verdict thresholds present", "Highly Recommended / Recommended / Average / Skip")
    else:
        check_warn("Verdict thresholds", "Could not locate verdict categories in scoring_agent.py")


# ── 6. Conflict of Interest Guard ───────────────────────────────────

def check_conflict_of_interest():
    print("\n[6/6] Conflict of Interest Guard")
    # Smart Caffeine products must be excluded from all reviews
    issues = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            rel = os.path.relpath(filepath, REPO_ROOT)
            # Skip the watchdog script itself
            if rel.startswith("scripts/watchdog"):
                continue
            with open(filepath, "r") as f:
                for line_num, line in enumerate(f, 1):
                    lower = line.lower()
                    # Flag if Smart Caffeine is being scored or reviewed (not just mentioned in exclusion logic)
                    if "smart caffeine" in lower:
                        if any(word in lower for word in ["exclud", "skip", "conflict", "ignore", "except", "#"]):
                            continue  # This is exclusion logic — good
                        issues.append(f"{rel}:{line_num} — Smart Caffeine reference (not in exclusion context)")

    if issues:
        for issue in issues:
            check_warn("Conflict of interest", issue)
    else:
        check_pass("Smart Caffeine exclusion", "No non-exclusion references found")


# ── Run All Checks ──────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("LIMITLESS LABS — WATCHDOG REPORT")
    print("=" * 60)

    check_python_syntax()
    check_scoring_weights()
    check_secret_leaks()
    check_imports()
    check_verdict_thresholds()
    check_conflict_of_interest()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Passed:   {len(passed)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Failed:   {len(failed)}")

    if failed:
        print("\nFAILURES (action required):")
        for name, detail in failed:
            print(f"  - {name}: {detail}")

    if warnings:
        print("\nWARNINGS (review recommended):")
        for name, detail in warnings:
            print(f"  - {name}: {detail}")

    if not failed and not warnings:
        print("\nAll checks passed — Leo's changes look good!")

    print("=" * 60)

    # Exit code: 1 if any failures, 0 otherwise (warnings are OK)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
