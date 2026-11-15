# Deploy CryptoOps Sentinel on Streamlit Community Cloud — $0

This folder is the **free-hosting edition** of v0.4.1.

## What changes versus Docker

- Streamlit hosts the UI. FastAPI handlers are invoked **in-process** via ASGI, with no separately hosted API server.
- Market prices are public **Kraken REST snapshots**, refreshed during active viewing; the continuous WebSocket worker is intentionally disabled.
- Database defaults to **local SQLite**, which is **ephemeral on Community Cloud**. Do not depend on stored market snapshots across restarts or claim 24/7 operational monitoring.
- News uses the existing GDELT/RSS logic and depends on the providers being reachable. External feeds can rate-limit.
- Paper holdings remain **fictional**. No private keys or exchange account access are needed.
- Heavy traffic, frequent automatic refresh, or provider rate limits may affect operation.

## Setup

1. Verify the repo has no secrets, and push it to GitHub.
2. Open https://share.streamlit.io/ and sign in with GitHub.
3. Create app -> Existing app; select your repository and branch (`main`).
4. **Main file path: `dashboard/cloud_app.py`**.
5. Set the Python version to a supported version compatible with the project's `>=3.11` requirement (3.11 or 3.12 is a sensible choice when offered).
6. Deploy. Your public URL should have the form `https://your-name.streamlit.app`.
7. Test markets, recent headlines, paper portfolio, glossary, and the selected historical date.
8. Add that **actual** URL and your GitHub repository URL to your resume.

### Required files

`requirements.txt` installs the Python package in editable mode (`-e .`), and `pyproject.toml` describes its dependencies.

### Important notes

- Never commit a `.env` file or real credentials. Public Kraken REST endpoints do **not** need API keys.
- This free-hosted mode is a demonstration, **not** a production trading or monitoring service.
- For the complete API server, WebSocket background worker, and PostgreSQL deployment, see the original Docker release.
- If you see a package install error, check Streamlit app logs, the selected Python version, and whether `-e .` was installed from the repository root.

## Hide the Deploy button

The included `.streamlit/config.toml` sets `[client] toolbarMode = "viewer"`. This hides developer options such as the Deploy button without relying on fragile CSS selectors.

## Publishing instructions

1. Push all files, including `.streamlit/config.toml`, to a public GitHub repository, after checking that no secret is committed.
2. Open https://share.streamlit.io, sign in with GitHub, and click **Create app**.
3. Choose repository and branch `main`, enter the **Main file path** `dashboard/cloud_app.py`.
4. Deploy, test the public link in an incognito browser, and put the actual URL on your CV.

The free edition uses ephemeral SQLite and Kraken REST polling instead of continuously running Docker services. It is a portfolio demonstration, not live trading infrastructure.
