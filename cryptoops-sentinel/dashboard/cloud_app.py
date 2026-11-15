
"""Streamlit Community Cloud entrypoint for CryptoOps Sentinel."""

import os
import sys
from pathlib import Path

# Use temporary, writable SQLite storage on Streamlit Cloud.
# This database is ephemeral and may reset when the app restarts.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:////tmp/cryptoops_sentinel_demo.db",
)

# Make the application packages importable.
ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Execute the original Streamlit dashboard.
APP = ROOT / "dashboard" / "app.py"

exec(
    compile(APP.read_text(encoding="utf-8"), str(APP), "exec")
)
