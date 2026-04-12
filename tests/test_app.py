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


# ── 7. Watchlist endpoint tests ─────────────────────────────────────────────


def test_watchlist_empty(client):
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json() == []


def _sample_watchlist_trade():
    return {
        "ticker": "aapl",
        "strategy": "bull-put-spread",
        "expiry": "2026-05-16",
        "legs": [
            {"type": "put", "action": "sell", "strike": 220, "original_mid": 3.50},
            {"type": "put", "action": "buy", "strike": 210, "original_mid": 1.20},
        ],
        "original_credit": 2.30,
        "original_return_pct": 29.9,
        "stock_price_at_save": 228.50,
    }


def test_watchlist_add_and_list(client):
    resp = client.post("/api/watchlist", json=_sample_watchlist_trade())
    assert resp.status_code == 200
    assert "id" in resp.json()

    items = client.get("/api/watchlist").json()
    assert len(items) == 1
    assert items[0]["ticker"] == "AAPL"
    assert items[0]["strategy"] == "bull-put-spread"
    assert items[0]["original_credit"] == 2.30
    assert "saved_at" in items[0]
    assert "id" in items[0]


def test_watchlist_reject_invalid_ticker(client):
    trade = _sample_watchlist_trade()
    trade["ticker"] = "AAPL1"
    resp = client.post("/api/watchlist", json=trade)
    assert resp.status_code == 400


def test_watchlist_delete(client):
    resp = client.post("/api/watchlist", json=_sample_watchlist_trade())
    item_id = resp.json()["id"]
    resp = client.delete(f"/api/watchlist/{item_id}")
    assert resp.status_code == 200
    assert client.get("/api/watchlist").json() == []


def test_watchlist_delete_missing(client):
    resp = client.delete("/api/watchlist/nonexistent")
    assert resp.status_code == 404


# ── Zone classification boundary tests ──────────────────────────────────────
#
# Safety net for _classify_zone_spread and _classify_zone_covered_call.
# Tests match the guidance table at tools.py:180 exactly.

from app.portfolio import _classify_zone_spread, _classify_zone_covered_call


class TestZoneSpreadStandardDTE:
    """Standard DTE (6–29), buf_adj=0.

    Buffer bands: SAFE >8, WATCH 4–8, WARNING 2–4, DANGER 0–2, ACT NOW ≤0
    Loss bands:   SAFE <20, WATCH 20–40, WARNING 40–65, DANGER 65–85, ACT NOW >85
    """

    def test_safe(self):
        assert _classify_zone_spread(15, 5, 20) == "SAFE"

    def test_safe_boundary(self):
        assert _classify_zone_spread(8.5, 19, 20) == "SAFE"

    def test_watch_at_buffer_8(self):
        assert _classify_zone_spread(8, 5, 20) == "WATCH"

    def test_watch_mid_band(self):
        assert _classify_zone_spread(6, 10, 20) == "WATCH"

    def test_watch_at_buffer_5(self):
        assert _classify_zone_spread(5, 10, 20) == "WATCH"

    def test_warning_at_buffer_4(self):
        assert _classify_zone_spread(4, 10, 20) == "WARNING"

    def test_warning_at_buffer_3(self):
        assert _classify_zone_spread(3, 10, 20) == "WARNING"

    def test_danger_at_buffer_2(self):
        assert _classify_zone_spread(2, 10, 20) == "DANGER"

    def test_danger_at_buffer_1(self):
        assert _classify_zone_spread(1, 10, 20) == "DANGER"

    def test_danger_fractional(self):
        assert _classify_zone_spread(0.5, 10, 20) == "DANGER"

    def test_act_now_at_buffer_0(self):
        assert _classify_zone_spread(0, 10, 20) == "ACT NOW"

    def test_act_now_negative_buffer(self):
        assert _classify_zone_spread(-5, 10, 20) == "ACT NOW"

    def test_act_now_loss_86(self):
        assert _classify_zone_spread(15, 86, 20) == "ACT NOW"


class TestZoneSpreadShortDTE:
    """Short DTE (≤5), buf_adj=+1. All buffer thresholds shift up by 1."""

    def test_safe(self):
        assert _classify_zone_spread(15, 5, 3) == "SAFE"

    def test_safe_needs_deeper_buffer(self):
        # At standard DTE buffer=9 is SAFE; at short DTE 9 <= 9 → WATCH.
        assert _classify_zone_spread(9, 5, 3) == "WATCH"

    def test_safe_at_buffer_10(self):
        assert _classify_zone_spread(10, 5, 3) == "SAFE"

    def test_watch_at_buffer_6(self):
        assert _classify_zone_spread(6, 10, 3) == "WATCH"

    def test_warning_at_buffer_5(self):
        assert _classify_zone_spread(5, 10, 3) == "WARNING"

    def test_warning_at_buffer_4(self):
        assert _classify_zone_spread(4, 10, 3) == "WARNING"

    def test_danger_at_buffer_3(self):
        assert _classify_zone_spread(3, 10, 3) == "DANGER"

    def test_danger_at_buffer_1(self):
        assert _classify_zone_spread(1, 10, 3) == "DANGER"

    def test_dte_5_boundary(self):
        assert _classify_zone_spread(3, 10, 5) == "DANGER"

    def test_dte_6_uses_standard(self):
        # buffer=3 at DTE=6 is WARNING (standard), not DANGER (short).
        assert _classify_zone_spread(3, 10, 6) == "WARNING"


class TestZoneSpreadLongDTE:
    """Long DTE (≥30), buf_adj=-1. All buffer thresholds shift down by 1."""

    def test_safe_at_buffer_8(self):
        assert _classify_zone_spread(8, 5, 45) == "SAFE"

    def test_watch_at_buffer_7(self):
        assert _classify_zone_spread(7, 5, 45) == "WATCH"

    def test_warning_at_buffer_3(self):
        assert _classify_zone_spread(3, 10, 45) == "WARNING"

    def test_danger_at_buffer_1(self):
        assert _classify_zone_spread(1, 10, 45) == "DANGER"

    def test_watch_at_buffer_4(self):
        # At standard DTE this is WARNING; at long DTE, WARNING requires ≤3.
        assert _classify_zone_spread(4, 10, 45) == "WATCH"

    def test_dte_30_uses_long_table(self):
        assert _classify_zone_spread(1, 10, 30) == "DANGER"

    def test_dte_29_uses_standard(self):
        assert _classify_zone_spread(1, 10, 29) == "DANGER"


class TestZoneSpreadLossDimension:
    """Loss-dimension cascades at standard DTE (buffer=15, deep enough to not matter).

    Loss bands: SAFE <20, WATCH 20–40, WARNING 40–65, DANGER 65–85, ACT NOW >85
    """

    def test_safe_low_loss(self):
        assert _classify_zone_spread(15, 10, 20) == "SAFE"

    def test_safe_at_loss_20(self):
        # loss > 20 triggers WATCH; loss == 20 exactly is still SAFE.
        assert _classify_zone_spread(15, 20, 20) == "SAFE"

    def test_watch_at_loss_21(self):
        assert _classify_zone_spread(15, 21, 20) == "WATCH"

    def test_watch_at_loss_30(self):
        assert _classify_zone_spread(15, 30, 20) == "WATCH"

    def test_watch_at_loss_40(self):
        assert _classify_zone_spread(15, 40, 20) == "WATCH"

    def test_warning_at_loss_41(self):
        assert _classify_zone_spread(15, 41, 20) == "WARNING"

    def test_warning_at_loss_65(self):
        assert _classify_zone_spread(15, 65, 20) == "WARNING"

    def test_danger_at_loss_66(self):
        assert _classify_zone_spread(15, 66, 20) == "DANGER"

    def test_danger_at_loss_85(self):
        assert _classify_zone_spread(15, 85, 20) == "DANGER"

    def test_act_now_at_loss_86(self):
        assert _classify_zone_spread(15, 86, 20) == "ACT NOW"


class TestZoneSpreadCombined:
    """When buffer and loss disagree, the worse zone wins."""

    def test_safe_buffer_bad_loss_wins(self):
        # buffer=15 → SAFE, but loss=50 → WARNING. WARNING wins.
        assert _classify_zone_spread(15, 50, 20) == "WARNING"

    def test_danger_buffer_safe_loss(self):
        # buffer=1 → DANGER, loss=5 → SAFE. DANGER wins.
        assert _classify_zone_spread(1, 5, 20) == "DANGER"

    def test_both_danger(self):
        assert _classify_zone_spread(1.5, 70, 20) == "DANGER"


class TestZoneCoveredCall:
    """_classify_zone_covered_call uses buffer_pct and call_value/credit ratio."""

    def test_safe(self):
        assert _classify_zone_covered_call(15, 0.5, 1.0, 30) == "SAFE"

    def test_watch_buffer_8(self):
        # buffer <= 8 → WATCH
        assert _classify_zone_covered_call(8, 0.5, 1.0, 30) == "WATCH"

    def test_watch_via_ratio(self):
        # ratio > 1.5 but <= 2
        assert _classify_zone_covered_call(15, 1.6, 1.0, 30) == "WATCH"

    def test_warning_buffer_4(self):
        assert _classify_zone_covered_call(4, 0.5, 1.0, 30) == "WARNING"

    def test_warning_via_ratio(self):
        assert _classify_zone_covered_call(15, 2.5, 1.0, 30) == "WARNING"

    def test_danger_buffer_2(self):
        assert _classify_zone_covered_call(2, 0.5, 1.0, 30) == "DANGER"

    def test_danger_via_ratio(self):
        assert _classify_zone_covered_call(15, 4.0, 1.0, 30) == "DANGER"

    def test_act_now_buffer_0(self):
        assert _classify_zone_covered_call(0, 0.5, 1.0, 30) == "ACT NOW"

    def test_act_now_via_ratio(self):
        assert _classify_zone_covered_call(15, 6.0, 1.0, 30) == "ACT NOW"

    def test_zero_credit_ratio_falls_to_zero(self):
        # ratio = 0 when credit is 0 → only buffer matters
        assert _classify_zone_covered_call(15, 5.0, 0, 30) == "SAFE"
