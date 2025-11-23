import sys
from pathlib import Path

# Add project root to PYTHONPATH for pytest runs
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
