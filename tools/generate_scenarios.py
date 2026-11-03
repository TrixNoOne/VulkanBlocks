import json
import random
import os

def generate_100_scenarios():
    random.seed(42)
    os.makedirs("vectors", exist_ok=True)
    
    scenarios = []
    for i in range(100):
        is_valid = random.choice([True, False])
        scenarios.append({
            "id": f"rand_{i}",
            "valid": is_valid,
            "status": "accepted" if is_valid else "rejected",
            "reason": None if is_valid else random.choice(["bad-pow", "bad-target", "bad-cb-height"])
        })
        
    with open("vectors/scripts.json", "w") as f:
        json.dump(scenarios, f, indent=2)
    print("Generated 100 seeded scenarios in vectors/scripts.json")

if __name__ == "__main__":
    generate_100_scenarios()
