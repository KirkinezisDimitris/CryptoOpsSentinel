# CryptoOps Sentinel — One-click local demo (Windows)

## Quick start

1. Install **Python 3.11+** from https://www.python.org/downloads/windows/ if you do not already have it. Enable **Add Python to PATH** when installing.
2. Extract this ZIP. Double-click **`START-WINDOWS.cmd`**.
3. On first launch, let the script download/install Python dependencies (internet required). Later launches reuse the local virtual environment.
4. The browser should open **http://localhost:8501**. If it does not, paste that URL into your browser.
5. Close the command window (or press Ctrl+C) to stop.

**No Docker, VPS, API key, or paid hosting required.** Kraken and news endpoints still require an internet connection and may rate-limit.

### Important limitations

- Small **download** (source code only), not a standalone `.exe`. Python must be installed once, and initial installation downloads dependencies. The installed Python packages are much larger than the ZIP.
- This edition uses in-process FastAPI and local SQLite. It runs on the user's own computer and has **no continuous WebSocket background worker**, hosted API, or shared persistent database.
- All holdings and trade-oriented signals are educational/simulated, not personal financial advice.
- A resume reviewer is usually better served by a clickable public Streamlit Community Cloud demo; this is an optional download for technical reviewers.
- Only run code you trust. Inspect `START-WINDOWS.cmd`, the Python sources, and `pyproject.toml` before running.

### Troubleshooting

Run `py -3 --version` to check Python, or open Command Prompt in the extracted folder and run `START-WINDOWS.cmd` to inspect errors. If your system has no `py` launcher, `python --version` is the alternative. If another app already uses port 8501, stop it first.
