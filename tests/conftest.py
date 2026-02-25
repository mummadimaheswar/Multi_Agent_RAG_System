import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Configure pytest-asyncio to auto-detect async test functions
pytest_plugins = ["pytest_asyncio"]
