import sys
from pathlib import Path

# Make `core` importable when running tests from the reference/ directory.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))