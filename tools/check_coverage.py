#!/usr/bin/env python
"""Coverage gate for the Vulkan oracle.

Runs pytest with branch coverage using .coveragerc-honest and exits non-zero
unless chain.py, script.py and storage.py are each at least 92% and every
other core module is at least 90%.

Usage (from repo root):
    python tools/check_coverage.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGERC = ROOT / ".coveragerc-honest"
JSON_REPORT = ROOT / "coverage.json"

# Minimum branch coverage thresholds.
CORE_TARGETS = {"chain.py", "script.py", "storage.py"}
CORE_MIN = 92.0
OTHER_MIN = 90.0

# Consensus-required lines: these must be covered unless a PROOF entry exists
# in docs/pragmas.md. Format: (file, line_number).
CONSENSUS_REQUIRED = {
    ("chain.py", 379),
    ("chain.py", 389),
    ("chain.py", 390),
    ("chain.py", 631),
    ("chain.py", 632),
    ("chain.py", 642),
    ("chain.py", 662),
    ("chain.py", 663),
    ("chain.py", 667),
    ("chain.py", 686),
    ("chain.py", 687),
    ("chain.py", 691),
    ("chain.py", 696),
    ("chain.py", 705),
    ("chain.py", 788),
    ("chain.py", 805),
    ("chain.py", 809),
    ("chain.py", 823),
    ("chain.py", 833),
    ("chain.py", 834),
    ("chain.py", 836),
    ("chain.py", 838),
    ("chain.py", 843),
    ("chain.py", 844),
    ("chain.py", 849),
    ("chain.py", 850),
    ("chain.py", 854),
    ("chain.py", 891),
    ("chain.py", 892),
    ("chain.py", 902),
    ("chain.py", 958),
    ("chain.py", 962),
    ("chain.py", 968),
    ("chain.py", 971),
    ("chain.py", 1029),
    ("chain.py", 1031),
    ("chain.py", 1081),
    ("chain.py", 1084),
    ("chain.py", 1089),
    ("chain.py", 1092),
    ("chain.py", 1095),
}


def main() -> int:
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=reference/core",
        "--cov-branch",
        f"--cov-config={COVERAGERC}",
        "--cov-report=json",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    # Print pytest output.
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Read JSON report.
    if not JSON_REPORT.exists():
        print("ERROR: coverage.json not generated", file=sys.stderr)
        return 1

    data = json.loads(JSON_REPORT.read_text(encoding="utf-8"))
    files = data.get("files", {})

    # Build per-file table.
    print()
    print(f"{'File':<30} {'Stmts':>6} {'Miss':>5} {'Branch':>7} {'BrPart':>7} {'Cover':>7}")
    print("-" * 70)

    failed = False
    for path, info in sorted(files.items()):
        if "core" not in path:
            continue
        name = Path(path).name
        stmts = info.get("summary", {}).get("num_statements", 0)
        miss = info.get("summary", {}).get("missing_lines", 0)
        branch = info.get("summary", {}).get("num_branches", 0)
        brpart = info.get("summary", {}).get("num_partial_branches", 0)
        cover = info.get("summary", {}).get("percent_covered", 0.0)

        print(f"{name:<30} {stmts:>6} {miss:>5} {branch:>7} {brpart:>7} {cover:>6.1f}%")

        if name in CORE_TARGETS:
            if cover < CORE_MIN:
                print(f"  FAIL: {name} at {cover:.1f}% < {CORE_MIN}%")
                failed = True
        else:
            if cover < OTHER_MIN:
                print(f"  FAIL: {name} at {cover:.1f}% < {OTHER_MIN}%")
                failed = True

    print("-" * 70)
    total_cover = data.get("totals", {}).get("percent_covered", 0.0)
    print(f"{'TOTAL':<30} {'':>6} {'':>5} {'':>7} {'':>7} {total_cover:>6.1f}%")
    print()

    # Check CONSENSUS_REQUIRED lines.
    pragmas_path = ROOT / "docs" / "pragmas.md"
    pragmas_text = pragmas_path.read_text(encoding="utf-8") if pragmas_path.exists() else ""

    for path, info in files.items():
        if "core" not in path:
            continue
        name = Path(path).name
        missing_lines = set(info.get("missing_lines", []))
        missing_branches = info.get("missing_branches", [])
        # Collect all uncovered line numbers (including branch targets).
        uncovered = set(missing_lines)
        for br in missing_branches:
            if isinstance(br, list) and len(br) >= 2:
                uncovered.add(br[1])

        for (req_file, req_line) in CONSENSUS_REQUIRED:
            if req_file != name:
                continue
            if req_line in uncovered:
                # Check for PROOF entry in docs/pragmas.md.
                proof_marker = f"PROOF: {req_file}:{req_line}"
                if proof_marker not in pragmas_text:
                    print(f"  CONSENSUS FAIL: {req_file}:{req_line} uncovered and no PROOF entry")
                    failed = True

    if failed:
        print("COVERAGE GATE: FAILED")
        return 1
    else:
        print("COVERAGE GATE: PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
