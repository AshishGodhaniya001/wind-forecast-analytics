"""Tests for the health endpoint (Step 2 scaffold)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import APP_NAME, app

client = TestClient(app)


def test_health_returns_200_and_ok_status() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == APP_NAME
    assert body["version"] == app.version


def test_health_timestamp_is_utc_iso8601() -> None:
    body = client.get("/api/health").json()

    # Example: 2026-01-01T12:00:00.123456+00:00
    assert body["timestamp"].endswith("+00:00")


def test_health_exposes_no_data_or_metrics() -> None:
    """The scaffold must not pretend to return analysis results."""
    body = client.get("/api/health").json()

    assert set(body) == {"status", "service", "version", "timestamp"}


def test_unknown_route_returns_404() -> None:
    assert client.get("/api/does-not-exist").status_code == 404
