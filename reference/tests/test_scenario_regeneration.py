# reference/tests/test_scenario_regeneration.py
import json
import os
import subprocess

def test_scenario_regeneration():
    with open("vectors/scripts.json", "r") as f:
        original = f.read()
    
    subprocess.run(["python", "tools/generate_scenarios.py"], check=True)
    
    with open("vectors/scripts.json", "r") as f:
        regenerated = f.read()
        
    assert original == regenerated, "Scenario regeneration is not byte-identical!"