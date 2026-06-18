"""Make `src/` importable without an install (Phase 1 convenience)."""
import pathlib
import sys

_SRC = pathlib.Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
