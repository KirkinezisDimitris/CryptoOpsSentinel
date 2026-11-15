"""Regression checks for the dashboard import failure in v0.4.0."""
from __future__ import annotations

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_dashboard_chart_modules_import():
    from dashboard.charts import ALLOCATION_STYLES, EQUITY_STYLES, PRICE_STYLES
    from dashboard.tables import present_table
    assert "Candlestick" in PRICE_STYLES
    assert ALLOCATION_STYLES and EQUITY_STYLES
    assert callable(present_table)


def test_both_packages_are_in_distributable_wheel():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    includes = config["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "cryptoops*" in includes
    assert "dashboard*" in includes


def test_streamlit_container_has_project_import_path():
    dockerfile = (ROOT / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "PYTHONPATH=/app" in dockerfile
    assert "PYTHONPATH: /app" in compose
