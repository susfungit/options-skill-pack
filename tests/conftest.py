"""Shared test fixtures — all external calls mocked, no API keys needed."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import DEFAULT_PROFILE


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect portfolio.json and profile.json to temp files."""
    portfolio_path = str(tmp_path / "portfolio.json")
    profile_path = str(tmp_path / "profile.json")

    with open(portfolio_path, "w") as f:
        json.dump([], f)
    with open(profile_path, "w") as f:
        json.dump(DEFAULT_PROFILE, f)

    trade_plans_dir = str(tmp_path / "trade-plans")

    monkeypatch.setattr("app.config.PORTFOLIO_PATH", portfolio_path)
    monkeypatch.setattr("app.config.PROFILE_PATH", profile_path)
    monkeypatch.setattr("app.config.TRADE_PLANS_DIR", trade_plans_dir)
    # Disable auth in tests so endpoints are accessible
    monkeypatch.setattr("app.auth._APP_API_KEY", None)
    # Reset lazy client so it doesn't leak between tests
    monkeypatch.setattr("app.chat._client", None)
    # Clear in-memory trade-plan jobs between tests
    from app import trade_plan_runner
    trade_plan_runner._JOBS.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_position():
    return {
        "label": "Test BPS",
        "strategy": "bull-put-spread",
        "ticker": "AAPL",
        "legs": [
            {"type": "put", "action": "sell", "strike": 180.0, "price": 3.50},
            {"type": "put", "action": "buy", "strike": 170.0, "price": 1.20},
        ],
        "net_credit": 2.30,
        "expiry": "2026-05-16",
        "contracts": 1,
    }
