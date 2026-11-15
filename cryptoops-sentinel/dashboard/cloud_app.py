"""Streamlit Community Cloud entrypoint for CryptoOps Sentinel."""
from pathlib import Path
import sys

# Allow direct execution from dashboard/ while keeping repository-root imports.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The original dashboard is executed via Streamlit's normal entrypoint path.
exec(compile((ROOT / "dashboard" / "app.py").read_text(encoding="utf-8"), str(ROOT / "dashboard" / "app.py"), "exec"))
