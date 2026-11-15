# CryptoOps Sentinel v0.4.1 — Startup fix

The Streamlit dashboard imports `dashboard.charts` and `dashboard.tables`, but the v0.4.0 wheel build only packaged `cryptoops`. This can cause a `ModuleNotFoundError` when Streamlit starts in Docker, depending on `sys.path`.

Fixes:
- `pyproject.toml`: explicitly include both `cryptoops*` and `dashboard*` in setuptools package discovery.
- `Dockerfile`: set `PYTHONPATH=/app` so the source package is importable when launching the Streamlit entrypoint.
- `docker-compose.yml`: set the same `PYTHONPATH` on the dashboard container.
- Tests: assert packaging and runtime-path safeguards.

No exchange connections were tested from this environment; only package imports, deterministic tests, and Docker/YAML syntax were validated. If the crash persists, capture the full traceback including the final exception line using `docker compose logs --tail=120 dashboard`.

Upgrade from v0.4.0:
```powershell
cd "$HOME\Downloads\cryptoops-sentinel-v0.4\cryptoops-sentinel"
docker compose down
cd "$HOME\Downloads\cryptoops-sentinel-v0.4.1\cryptoops-sentinel"
docker compose up --build -d
docker compose logs --tail=60 dashboard
```

**Do not** run `docker compose down -v`: it removes database volumes.
