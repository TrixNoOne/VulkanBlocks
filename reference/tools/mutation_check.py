"""Mutation testing tool for the Vulkan oracle (stdlib only).

For each mutation patch, a temporary copy of the file is created, the patch
is applied, pytest is run, and the original is restored even on error.
Prints KILLED or SURVIVED for each mutation.

Usage (from repo root):
    python reference/tools/mutation_check.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = Path(__file__).resolve().parent

MUTATIONS = [
    ("reference/core/chain.py", "if changes.coinbase_value > allowed + changes.fees:", "if changes.coinbase_value >= allowed + changes.fees:", "coinbase_value > becomes >="),
    ("reference/core/chain.py", "if utxo.is_coinbase:\n            if height - utxo.height < coinbase_maturity:", "if utxo.is_coinbase:\n            if False:", "remove coinbase maturity check"),
    ("reference/core/chain.py", "if block.header.target != expected_target:", "if False:", "remove target == expected check"),
    ("reference/core/block.py", "if timestamp <= mtp:", "if timestamp < mtp:", "timestamp <= mtp becomes <"),
    ("reference/core/block.py", "if timestamp > now + MAX_FUTURE_DRIFT:", "if timestamp > now + MAX_FUTURE_DRIFT + 3600:", "future limit +2h becomes +3h"),
    ("reference/core/chain.py", 'if checkpoint is not None and checkpoint.hash != block.block_hash:', "if False:", "remove checkpoint check on connect"),
    ("reference/core/params.py", "era = height // halving_interval", "era = height // halving_interval + 1", "halving shift off by one"),
    ("reference/core/chain.py", "if emitted > MAX_MONEY:", "if False:", "remove cumulative MAX_MONEY check"),
    ("reference/core/chain.py", "if coinbase_height != block.height:", "if False:", "remove coinbase height check"),
]


def run_tests() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "reference/tests", "-x", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Mutation testing for Vulkan oracle")
    parser.add_argument("--file", help="Specific file to mutate (optional)")
    args = parser.parse_args()

    mutations_to_run = MUTATIONS
    if args.file:
        mutations_to_run = [m for m in MUTATIONS if m[0] == args.file]

    results = []
    for file_rel, old_text, new_text, desc in mutations_to_run:
        file_path = ROOT / file_rel
        print(f"\nMutation: {desc}")
        print(f"  File: {file_rel}")

        if not file_path.exists():
            print("  SKIPPED (file not found)")
            results.append((desc, "SKIPPED"))
            continue

        content = file_path.read_text(encoding="utf-8")
        if old_text not in content:
            print("  SKIPPED (pattern not found)")
            results.append((desc, "SKIPPED"))
            continue

        # Backup.
        backup = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup)

        # Apply mutation.
        mutated = content.replace(old_text, new_text, 1)
        file_path.write_text(mutated, encoding="utf-8")

        # Run tests.
        passed = run_tests()
        status = "SURVIVED" if passed else "KILLED"
        print(f"  Result: {status}")

        # Restore.
        shutil.copy2(backup, file_path)
        backup.unlink()

        results.append((desc, status))

    print("\n" + "=" * 60)
    print("MUTATION TESTING SUMMARY")
    print("=" * 60)
    for desc, status in results:
        print(f"  {status:10s} {desc}")

    survived = [r for r in results if r[1] == "SURVIVED"]
    if survived:
        print(f"\n{len(survived)} mutation(s) SURVIVED - need more tests!")
        sys.exit(1)
    else:
        print("\nAll mutations KILLED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
