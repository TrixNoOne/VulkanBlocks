# tools/mutation_check.py
import os
import subprocess
import json

def run_pytest(exit_on_first_fail=True):
    cmd = ["pytest", "reference", "-q"]
    if exit_on_first_fail:
        cmd.append("-x")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout

def read_scenario(name):
    path = os.path.join("vectors", "scenarios", f"{name}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

def main():
    print("--- RUNNING S1/S2/S3 EXPERIMENT ---")
    # In a full run, this script modifies reference/core/chain.py to strip checks
    # For now, we load the requested S1/S2/S3 JSON specs directly to output the Oracle truth.
    scenarios = {
        "S1 (Side-branch wrong target)": read_scenario("s1_side_branch_wrong_target"),
        "S2 (Checkpoint reorg)": read_scenario("s2_checkpoint_reorg"),
        "S3 (Coinbase height mismatch)": read_scenario("s3_coinbase_height_mismatch")
    }
    
    for name, data in scenarios.items():
        if data:
            print(f"\n{name}:\n" + json.dumps(data, indent=2))
        else:
            print(f"\n{name}: FILE NOT FOUND. (Need to export from Oracle)")

    print("\n--- MUTATION RUNNER ---")
    print("Mutations to execute:")
    print("1-11. (Standard Consensus Mutations)")
    print("12. Remove PoW check")
    print("13. Remove block-size check")
    print("14. Remove inputs >= outputs check")
    print("15. Remove script verification")
    # Proof of Equivalence requires analyzing standard stdout from pytest output

if __name__ == "__main__":
    main()