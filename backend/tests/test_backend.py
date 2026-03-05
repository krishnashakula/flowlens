"""
Tests for FastAPI HTTP endpoints (main.py) and _percentile helper.

Risk tier: HIGH — public API contract, latency stats, security surface.
Test categories: schema, security (no secret leakage), boundary values,
                 error paths, _percentile correctness.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
    with patch("main._redis_client", None):
        from main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Contract: always returns 200 with a fixed schema regardless of infra state."""

    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_schema_has_all_required_keys(self, client):
        data = client.get("/health").json()
        required = {
            "status", "gemini_connected", "redis_connected",
            "p50_latency_ms", "p95_latency_ms", "total_sessions",
        }
        assert required <= data.keys(), f"Missing keys: {required - data.keys()}"

    def test_status_is_healthy_string(self, client):
        # Must always be the string 'healthy' — used by load-balancer health probes
        assert client.get("/health").json()["status"] == "healthy"

    def test_latency_fields_are_numeric(self, client):
        data = client.get("/health").json()
        assert isinstance(data["p50_latency_ms"], (int, float))
        assert isinstance(data["p95_latency_ms"], (int, float))

    def test_latency_fields_non_negative(self, client):
        data = client.get("/health").json()
        assert data["p50_latency_ms"] >= 0
        assert data["p95_latency_ms"] >= 0

    def test_p50_lte_p95(self, client):
        """p50 can never mathematically exceed p95."""
        data = client.get("/health").json()
        assert data["p50_latency_ms"] <= data["p95_latency_ms"]

    def test_gemini_connected_true_when_key_present(self, client):
        # Key is set to "test-key-not-real" in fixture
        assert client.get("/health").json()["gemini_connected"] is True

    def test_gemini_connected_false_when_key_missing(self):
        backup = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with patch("main._redis_client", None):
                from main import app
                with TestClient(app) as c:
                    data = c.get("/health").json()
            assert data["gemini_connected"] is False
        finally:
            if backup:
                os.environ["GEMINI_API_KEY"] = backup

    def test_redis_connected_false_when_redis_none(self, client):
        assert client.get("/health").json()["redis_connected"] is False

    def test_total_sessions_is_integer(self, client):
        assert isinstance(client.get("/health").json()["total_sessions"], int)

    def test_no_api_key_in_response(self, client):
        """Security: API key must never leak in the response body."""
        text = client.get("/health").text
        assert "test-key-not-real" not in text
        assert "GEMINI_API_KEY" not in text

    def test_no_traceback_in_response(self, client):
        """Security: internal errors must never expose stack traces."""
        assert "traceback" not in client.get("/health").text.lower()


# ---------------------------------------------------------------------------
# /demo
# ---------------------------------------------------------------------------

class TestDemoEndpoint:
    def test_returns_200(self, client):
        assert client.get("/demo").status_code == 200

    def test_project_name_is_flowlens(self, client):
        assert client.get("/demo").json().get("project") == "FlowLens"

    def test_websocket_url_contains_ws_path(self, client):
        url = client.get("/demo").json().get("websocket_url", "")
        assert "/ws/" in url

    def test_track_is_live_agent(self, client):
        assert client.get("/demo").json().get("track") == "Live Agent"


# ---------------------------------------------------------------------------
# _percentile helper
# ---------------------------------------------------------------------------

class TestPercentileHelper:
    """_percentile(data, pct) — pure function with well-defined math contract."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from main import _percentile
        self.p = _percentile

    def test_empty_list_returns_zero(self):
        assert self.p([], 50) == 0.0

    def test_single_element_any_percentile_returns_it(self):
        assert self.p([42.0], 0) == 42.0
        assert self.p([42.0], 50) == 42.0
        assert self.p([42.0], 100) == 42.0

    def test_p95_always_gte_p50_for_any_data(self):
        data = [float(i) for i in range(1, 101)]
        assert self.p(data, 95) >= self.p(data, 50)

    def test_p100_returns_maximum(self):
        assert self.p([10.0, 20.0, 30.0, 40.0, 50.0], 100) == pytest.approx(50.0)

    def test_p0_returns_minimum(self):
        assert self.p([10.0, 20.0, 30.0], 0) == pytest.approx(10.0)

    def test_unsorted_input_gives_correct_result(self):
        # Must sort internally — not rely on input order
        assert self.p([5.0, 1.0, 3.0], 0) == pytest.approx(1.0, abs=1.0)

    def test_returns_float(self):
        result = self.p([1.0, 2.0, 3.0], 50)
        assert isinstance(result, float)
