"""Shared test fixtures and path setup.

`pythonpath = .` in pytest.ini makes `app` importable. This file is the home for
cross-test fixtures (fake AI providers, in-memory repos) added in later phases.
"""
import sys
from pathlib import Path

# Belt-and-suspenders: ensure the backend root is importable even if pytest is
# invoked from elsewhere.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
