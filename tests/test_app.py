"""Tests for options-skill-pack. All external calls mocked — no API keys needed."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.tools import _validate_tool_input, _build_args, execute_tool


# ── 1. _validate_tool_input unit tests ──────────────────────────────────────


def test_validate_valid_input():
    assert _validate_tool_input({"short_strike": 180, "target_delta": 0.2, "expiry": "2026-05-16"}) is None


def test_validate_empty_input():
    assert _validate_tool_input({}) is None


def test_validate_negative_strike():
    err = _validate_tool_input({"short_strike": -5})
    assert err is not None and "short_strike" in err


def test_validate_zero_strike():
    err = _validate_tool_input({"short_strike": 0})
    assert err is not None and "short_strike" in err


def test_validate_delta_too_high():
    err = _validate_tool_input({"target_delta": 1.5})
    assert err is not None and "target_delta" in err


def test_validate_delta_zero():
    err = _validate_tool_input({"target_delta": 0})
    assert err is not None and "target_delta" in err


def test_validate_delta_one():
    err = _validate_tool_input({"target_delta": 1})
    assert err is not None and "target_delta" in err


def test_validate_delta_valid():
    assert _validate_tool_input({"target_delta": 0.2}) is None


def test_validate_dte_zero():
    err = _validate_tool_input({"dte_min": 0})
    assert err is not None and "dte_min" in err


def test_validate_dte_negative():
    err = _validate_tool_input({"dte_max": -10})
    assert err is not None and "dte_max" in err


def test_validate_bad_expiry_format():
    err = _validate_tool_input({"expiry": "05-16-2026"})
    assert err is not None and "expiry" in err


def test_validate_expiry_not_string():
    err = _validate_tool_input({"expiry": 20260516})
    assert err is not None and "expiry" in err


def test_validate_roll_side_invalid():
    err = _validate_tool_input({"roll_side": "both"})
    assert err is not None and "roll_side" in err


def test_validate_roll_side_valid():
    assert _validate_tool_input({"roll_side": "put"}) is None


@pytest.mark.parametrize("field", [
    "short_strike", "long_strike", "short_put", "long_put",
    "short_call", "long_call", "short_put_strike", "short_call_strike",
    "net_credit", "cost_basis", "spread_width",
])
def test_validate_positive_field_rejects_non_number(field):
    assert _validate_tool_input({field: "abc"}) is not None


# ── 2. execute_tool tests ───────────────────────────────────────────────────


def test_execute_tool_invalid_ticker():
    result = json.loads(execute_tool("find_bull_put_spread", {"ticker": "INVALID123"}))
    assert "error" in result
    assert "Invalid ticker" in result["error"]


def test_execute_tool_validation_failure():
    result = json.loads(execute_tool("find_bull_put_spread", {"ticker": "AAPL", "target_delta": 5}))
    assert "error" in result
    assert "target_delta" in result["error"]


def test_execute_tool_unknown_tool():
    result = json.loads(execute_tool("nonexistent_tool", {"ticker": "AAPL"}))
    assert "error" in result
    assert "Unknown tool" in result["error"]


@patch("app.tools.os.path.exists", return_value=True)
@patch("app.tools.subprocess.run")
def test_execute_tool_success(mock_run, mock_exists):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='{"result": "ok"}', stderr=""
    )
    result = json.loads(execute_tool("find_bull_put_spread", {"ticker": "AAPL"}))
    assert result == {"result": "ok"}
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "python3"
    assert "fetch_chain.py" in call_args[1]
    assert call_args[2] == "AAPL"


@patch("app.tools.os.path.exists", return_value=True)
@patch("app.tools.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="", timeout=30))
def test_execute_tool_timeout(mock_run, mock_exists):
    result = json.loads(execute_tool("find_bull_put_spread", {"ticker": "AAPL"}))
    assert "error" in result
    assert "timed out" in result["error"]


# ── 3. _build_args tests ───────────────────────────────────────────────────


def test_build_args_bull_put_ticker_only():
    assert _build_args("find_bull_put_spread", {"ticker": "AAPL"}) == ["AAPL"]


def test_build_args_bull_put_full():
    args = _build_args("find_bull_put_spread", {
        "ticker": "AAPL", "target_delta": 0.2, "dte_min": 35, "dte_max": 45, "spread_width": 10,
    })
    assert args == ["AAPL", "0.2", "35", "45", "10"]


def test_build_args_check_bull_put():
    args = _build_args("check_bull_put_spread", {
        "ticker": "SPY", "short_strike": 420, "long_strike": 410,
        "net_credit": 2.5, "expiry": "2026-05-16",
    })
    assert args == ["SPY", "420", "410", "2.5", "2026-05-16"]


# ── 4. Chat max iterations test ─────────────────────────────────────────────


@patch("app.chat.execute_tool", return_value='{"result": "ok"}')
@patch("app.chat.get_client")
def test_chat_max_iterations(mock_get_client, mock_exec, client):
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.name = "find_bull_put_spread"
    mock_tool_block.input = {"ticker": "AAPL"}
    mock_tool_block.id = "call_123"

    mock_response = MagicMock()
    mock_response.stop_reason = "tool_use"
    mock_response.content = [mock_tool_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    resp = client.post("/api/chat", json={"message": "test", "history": []})
    assert resp.status_code == 200
    data = resp.json()
    assert "Stopped" in data["response"]
    assert "Too many tool calls" in data["response"]
    # 1 initial + 5 rounds = 6 calls
    assert mock_client.messages.create.call_count == 6


# ── 5. Portfolio CRUD tests ──────────────────────────────────────────────────


def test_portfolio_list_empty(client):
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    assert resp.json() == []


def test_portfolio_add(client, sample_position):
    resp = client.post("/api/portfolio", json=sample_position)
    assert resp.status_code == 200
    pos_id = resp.json()["id"]
    assert pos_id

    portfolio = client.get("/api/portfolio").json()
    assert len(portfolio) == 1
    assert portfolio[0]["ticker"] == "AAPL"
    assert portfolio[0]["id"] == pos_id


def test_portfolio_update(client, sample_position):
    pos_id = client.post("/api/portfolio", json=sample_position).json()["id"]

    updated = sample_position.copy()
    updated["net_credit"] = 3.00
    resp = client.put(f"/api/portfolio/{pos_id}", json=updated)
    assert resp.status_code == 200

    portfolio = client.get("/api/portfolio").json()
    assert portfolio[0]["net_credit"] == 3.00


def test_portfolio_delete(client, sample_position):
    pos_id = client.post("/api/portfolio", json=sample_position).json()["id"]

    resp = client.delete(f"/api/portfolio/{pos_id}")
    assert resp.status_code == 200

    assert client.get("/api/portfolio").json() == []


def test_portfolio_delete_not_found(client):
    resp = client.delete("/api/portfolio/nonexistent")
    assert resp.status_code == 404


def test_portfolio_close(client, sample_position):
    pos_id = client.post("/api/portfolio", json=sample_position).json()["id"]

    resp = client.post(f"/api/portfolio/{pos_id}/close", json={"close_price": 0.50})
    assert resp.status_code == 200

    portfolio = client.get("/api/portfolio").json()
    assert portfolio[0]["status"] == "closed"
    # P&L = (2.30 - 0.50) * 100 * 1 = 180.0
    assert portfolio[0]["closed_pnl"] == 180.0


def test_portfolio_reopen(client, sample_position):
    pos_id = client.post("/api/portfolio", json=sample_position).json()["id"]
    client.post(f"/api/portfolio/{pos_id}/close", json={})

    resp = client.post(f"/api/portfolio/{pos_id}/reopen")
    assert resp.status_code == 200

    portfolio = client.get("/api/portfolio").json()
    assert portfolio[0]["status"] == "open"


# ── 6. Analyzer endpoint tests ──────────────────────────────────────────────


@patch("app.analyze.execute_tool", return_value='{"strikes": [180, 170]}')
def test_analyze_calls_correct_tool(mock_exec, client):
    resp = client.post("/api/analyze", json={"ticker": "AAPL", "strategy": "bull-put-spread"})
    assert resp.status_code == 200
    assert resp.json() == {"strikes": [180, 170]}
    mock_exec.assert_called_once()
    call_args = mock_exec.call_args
    assert call_args[0][0] == "find_bull_put_spread"
    assert call_args[0][1]["ticker"] == "AAPL"


def test_analyze_invalid_strategy(client):
    resp = client.post("/api/analyze", json={"ticker": "AAPL", "strategy": "butterfly"})
    assert resp.status_code == 422
