"""Tests for the Elexon HTTP client.

All responses here are synthetic and generated inside the test process. No
network access is used and none of these payloads are real API data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx
import pytest

from app.services.elexon_client import (
    ElexonAPIError,
    ElexonClient,
    FUELHH_PATH,
    WINDFOR_PATH,
)

UTC = timezone.utc
SAMPLE_ACTUAL = {
    "dataset": "FUELHH",
    "publishTime": "2026-01-01T00:30:00Z",
    "startTime": "2026-01-01T00:00:00Z",
    "settlementDate": "2026-01-01",
    "settlementPeriod": 1,
    "fuelType": "WIND",
    "generation": 13756,
}
SAMPLE_FORECAST = {
    "dataset": "WINDFOR",
    "publishTime": "2025-12-31T22:30:00Z",
    "startTime": "2026-01-01T00:00:00Z",
    "generation": 19960,
}


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_attempts: int = 3,
) -> tuple[ElexonClient, list[float]]:
    sleeps: list[float] = []
    client = ElexonClient(
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        backoff_seconds=0.0,
        max_attempts=max_attempts,
    )
    return client, sleeps


def json_response(request: httpx.Request, payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


# --------------------------------------------------------------------------
# Request construction (documented parameters only)
# --------------------------------------------------------------------------


def test_fuelhh_request_uses_documented_parameters() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return json_response(request, [SAMPLE_ACTUAL])

    client, _ = make_client(handler)
    with client:
        client.fetch_fuelhh_wind(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
        )

    url = seen[0]
    assert url.path.endswith(FUELHH_PATH)
    assert url.params["publishDateTimeFrom"] == "2026-01-01T00:00:00Z"
    assert url.params["publishDateTimeTo"] == "2026-02-01T00:00:00Z"
    assert url.params["fuelType"] == "WIND"
    # startTime filters are not used: WINDFOR ignores them and FUELHH does not
    # need them when the publication window is tight.
    assert "startTimeFrom" not in url.params


def test_windfor_request_always_sends_a_publication_window() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return json_response(request, [SAMPLE_FORECAST])

    client, _ = make_client(handler)
    with client:
        client.fetch_windfor(
            datetime(2025, 12, 30, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
        )

    url = seen[0]
    assert url.path.endswith(WINDFOR_PATH)
    # Without these the API returns only the latest published version, which
    # would silently introduce look-ahead bias.
    assert url.params["publishDateTimeFrom"] == "2025-12-30T00:00:00Z"
    assert url.params["publishDateTimeTo"] == "2026-02-01T00:00:00Z"


def test_naive_datetime_parameter_is_rejected() -> None:
    client, _ = make_client(lambda request: json_response(request, []))

    with client, pytest.raises(ValueError, match="timezone-aware"):
        client.fetch_windfor(datetime(2026, 1, 1), datetime(2026, 2, 1))


def test_publish_window_in_wrong_order_is_rejected() -> None:
    client, _ = make_client(lambda request: json_response(request, []))

    with client, pytest.raises(ValueError, match="must not be earlier"):
        client.fetch_windfor(
            datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
        )


# --------------------------------------------------------------------------
# Success path
# --------------------------------------------------------------------------


def test_records_are_returned_unchanged() -> None:
    client, _ = make_client(lambda request: json_response(request, [SAMPLE_FORECAST]))

    with client:
        records = client.fetch_windfor(
            datetime(2025, 12, 30, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
        )

    assert records == [SAMPLE_FORECAST]


def test_empty_list_is_a_valid_response() -> None:
    client, _ = make_client(lambda request: json_response(request, []))

    with client:
        assert client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        ) == []


# --------------------------------------------------------------------------
# Retry behaviour
# --------------------------------------------------------------------------


def test_retry_after_header_is_respected_on_429() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, request=request)
        return json_response(request, [SAMPLE_FORECAST])

    client, sleeps = make_client(handler)
    with client:
        records = client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert records == [SAMPLE_FORECAST]
    assert calls["n"] == 2
    assert sleeps == [7.0]


def test_transient_server_error_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, request=request)
        return json_response(request, [SAMPLE_ACTUAL])

    client, sleeps = make_client(handler)
    with client:
        records = client.fetch_fuelhh_wind(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert records == [SAMPLE_ACTUAL]
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_client_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request", request=request)

    client, sleeps = make_client(handler)

    with client, pytest.raises(ElexonAPIError, match="HTTP 400"):
        client.fetch_fuelhh_wind(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert calls["n"] == 1
    assert sleeps == []


def test_timeout_is_retried_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out")
        return json_response(request, [SAMPLE_FORECAST])

    client, sleeps = make_client(handler)
    with client:
        records = client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert records == [SAMPLE_FORECAST]
    assert calls["n"] == 2
    assert len(sleeps) == 1


def test_gives_up_after_max_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom", request=request)

    client, sleeps = make_client(handler, max_attempts=3)

    with client, pytest.raises(ElexonAPIError, match="after 3 attempt"):
        client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert len(sleeps) == 2


# --------------------------------------------------------------------------
# Unexpected payloads
# --------------------------------------------------------------------------


def test_non_list_payload_raises() -> None:
    client, _ = make_client(
        lambda request: json_response(request, {"error": "unexpected"})
    )

    with client, pytest.raises(ElexonAPIError, match="expected a list"):
        client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )


def test_list_of_non_objects_raises() -> None:
    client, _ = make_client(lambda request: json_response(request, [[1, 2, 3]]))

    with client, pytest.raises(ElexonAPIError, match="expected an object"):
        client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )


def test_invalid_json_raises() -> None:
    client, _ = make_client(
        lambda request: httpx.Response(200, text="<html>nope</html>", request=request)
    )

    with client, pytest.raises(ElexonAPIError, match="not valid JSON"):
        client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )
