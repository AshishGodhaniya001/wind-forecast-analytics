"""Tests for the analysis API endpoints.

Every fixture here is a small synthetic artefact written to a temporary
directory. None of it is used as production data or as a fallback when the real
outputs are missing. Two extra tests compare the API against the real generated
January 2026 files when those files are present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.analysis_store import (
    ALIGNED_FILENAME,
    REPORT_FILENAME,
    AnalysisStore,
    get_analysis_store,
)

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

LIMITATIONS = [
    "The cutoff time is a provisional assumption, not a company requirement.",
    (
        "WINDFOR startTime interval semantics are stated only indirectly, so "
        "shifting the forecast by one hour would change the results."
    ),
    (
        "The two datasets may not cover the same generation population. Mean "
        "forecast generation is higher than mean actual generation; metrics are "
        "reported raw."
    ),
]


# --------------------------------------------------------------------------
# Synthetic artefacts
# --------------------------------------------------------------------------


def make_report() -> dict:
    """A two-hour report whose sections all agree with each other."""
    return {
        "generated_at": "2026-02-01T00:00:00Z",
        "analysis_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T02:00:00Z",
            "interval": "half-open [start, end)",
            "timezone": "UTC",
            "expected_hours": 2,
        },
        "cutoff_assumption": {
            "rule": (
                "For delivery day D (Europe/London), the latest forecast whose "
                "publishTime is strictly earlier than 09:20 Europe/London on D-1."
            ),
            "status": "provisional assumption",
            "not_prescribed_by_challenge": True,
            "rationale": "Chosen as the smallest defensible reading of the brief.",
        },
        "period_labelling": (
            "startTime marks the START of the interval it describes. No "
            "timestamp is shifted."
        ),
        "sources": {
            "actuals": {
                "file": "actuals_january_2026.json",
                "records": 4,
                "resolution_seconds": 1800,
            },
            "forecasts": {
                "file": "forecasts_january_2026.json",
                "versions": 6,
                "targets": 2,
                "resolution_seconds": 3600,
            },
        },
        "counts": {
            "actual_source_records": 4,
            "valid_hourly_actuals": 2,
            "unavailable_hourly_actuals": 0,
            "forecast_versions_for_january_targets": 6,
            "forecast_targets": 2,
            "selected_forecasts": 2,
            "missing_forecasts": 0,
            "conflicting_latest_publications": 0,
            "collapsed_duplicate_publications": 0,
            "missing_actuals_for_selected_forecasts": 0,
            "unmatched_targets": 0,
            "valid_aligned_pairs": 2,
        },
        "metrics": {
            "pair_count": 2,
            "mae_mw": 15.0,
            "rmse_mw": 15.811,
            "bias_mw": -5.0,
            "nmae_percent": 10.0,
            "mean_actual_mw": 150.0,
            "mean_forecast_mw": 145.0,
            "note": None,
        },
        "headline_metrics": {
            "overforecast_share_percent": 50.0,
            "rmse_after_bias_mw": 15.0,
            "bias_squared_error_share_percent": 10.0,
            "bias_percent_of_mean_actual": -3.3333,
            "headline_text": "Forecasts ran below actual in this test fixture.",
        },
        "additional_metrics": {
            "p90_absolute_error_mw": 19.0,
            "p95_absolute_error_mw": 19.5,
            "largest_miss": {
                "target_start": "2026-01-01T01:00:00Z",
                "date_utc": "2026-01-01",
                "hour_utc": 1,
                "absolute_error_mw": 20.0,
                "error_mw": -20.0,
                "actual_mw": 200.0,
                "forecast_mw": 180.0,
            },
            "scatter_peak_caption": "Forecast peaks reach about 0 GW while actuals top out near 0.0 GW.",
            "naive_previous_day_baseline": {
                "pair_count": 0,
                "mae_mw": None,
                "rmse_mw": None,
            },
            "mae_reduction_vs_naive_percent": None,
            "by_lead_time_bucket": [
                {
                    "bucket": label,
                    "pair_count": 2 if label == "<6h" else 0,
                    "mae_mw": 15.0 if label == "<6h" else None,
                    "bias_mw": -5.0 if label == "<6h" else None,
                }
                for label in (
                    "<6h", "6-12h", "12-18h", "18-24h", "24-30h", "30-36h", "36-40h", ">=40h"
                )
            ],
            "by_hour_of_day": [
                {
                    "hour_utc": hour,
                    "pair_count": 1 if hour in (0, 1) else 0,
                    "mae_mw": 10.0 if hour == 0 else 20.0 if hour == 1 else None,
                    "bias_mw": 10.0 if hour == 0 else -20.0 if hour == 1 else None,
                }
                for hour in range(24)
            ],
            "hour_of_day_mae_extremes": {
                "highest_hour_utc": 1,
                "highest_mae_mw": 20.0,
                "lowest_hour_utc": 0,
                "lowest_mae_mw": 10.0,
            },
            "worst_days_by_mae": [
                {"date_utc": "2026-01-01", "pair_count": 2, "mae_mw": 15.0}
            ],
            "timestamp_sensitivity": [
                {"shift_hours": -1, "pair_count": 1, "mae_mw": 90.0, "bias_mw": -90.0},
                {"shift_hours": 0, "pair_count": 2, "mae_mw": 15.0, "bias_mw": -5.0},
                {"shift_hours": 1, "pair_count": 1, "mae_mw": 80.0, "bias_mw": 80.0},
            ],
        },
        "metric_definitions": {
            "error": "forecastMW - actualMW, in MW.",
            "mae_mw": "Mean of |error| across valid aligned pairs, in MW.",
            "rmse_mw": "Square root of the mean of error^2, in MW.",
            "bias_mw": "Mean of error, in MW.",
            "nmae_percent": "MAE divided by mean actual MW, times 100.",
            "mape": "Not used. Percentage error against low actual generation is unstable.",
        },
        "lead_time_hours": {
            "count": 2,
            "min_hours": 1.5,
            "median_hours": 1.75,
            "mean_hours": 1.75,
            "max_hours": 2.0,
            "p05_hours": 1.525,
            "p95_hours": 1.975,
            "buckets": {
                "<6h": 2,
                "6-12h": 0,
                "12-18h": 0,
                "18-24h": 0,
                "24-30h": 0,
                "30-36h": 0,
                "36-40h": 0,
                ">=40h": 0,
            },
        },
        "audit": {
            "missing_forecast": [],
            "missing_actual": [],
            "conflicting_latest_publications": [],
            "unavailable_hourly_actuals": [],
        },
        "limitations": list(LIMITATIONS),
    }


def make_aligned() -> dict:
    return {
        "dataset": "aligned-pairs",
        "description": "Hourly actual and selected forecast matched by target interval.",
        "derived": True,
        "pair_count": 2,
        "records": [
            {
                "targetStart": "2026-01-01T00:00:00Z",
                "actualMW": 100.0,
                "forecastMW": 110.0,
                "errorMW": 10.0,
                "forecastPublishTime": "2025-12-31T22:30:00Z",
                "leadHours": 1.5,
            },
            {
                "targetStart": "2026-01-01T01:00:00Z",
                "actualMW": 200.0,
                "forecastMW": 180.0,
                "errorMW": -20.0,
                "forecastPublishTime": "2025-12-31T23:00:00Z",
                "leadHours": 2.0,
            },
        ],
    }


def write_json(directory: Path, filename: str, payload: dict) -> None:
    (directory / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_bundle(directory: Path) -> None:
    write_json(directory, REPORT_FILENAME, make_report())
    write_json(directory, ALIGNED_FILENAME, make_aligned())


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    write_bundle(tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir: Path):
    app.dependency_overrides[get_analysis_store] = lambda: AnalysisStore(data_dir)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# /api/analysis/summary
# --------------------------------------------------------------------------


def test_summary_returns_report_values(client: TestClient) -> None:
    response = client.get("/api/analysis/summary")

    assert response.status_code == 200
    body = response.json()

    assert body["generated_at"] == "2026-02-01T00:00:00Z"
    assert body["metrics"] == {
        "pair_count": 2,
        "mae_mw": 15.0,
        "rmse_mw": 15.811,
        "bias_mw": -5.0,
        "nmae_percent": 10.0,
        "mean_actual_mw": 150.0,
        "mean_forecast_mw": 145.0,
        "note": None,
    }
    assert body["headline_metrics"]["overforecast_share_percent"] == 50.0
    assert body["headline_metrics"]["rmse_after_bias_mw"] == 15.0
    assert body["additional_metrics"]["p95_absolute_error_mw"] == 19.5
    assert body["counts"]["valid_aligned_pairs"] == 2
    assert body["counts"]["missing_forecasts"] == 0
    assert body["analysis_window"]["timezone"] == "UTC"
    assert body["lead_time_hours"]["median_hours"] == 1.75
    assert body["cutoff_assumption"]["not_prescribed_by_challenge"] is True


def test_summary_includes_cutoff_and_both_key_limitations(client: TestClient) -> None:
    body = client.get("/api/analysis/summary").json()

    assert "strictly earlier than 09:20 Europe/London on D-1" in body["cutoff_assumption"]["rule"]
    joined = " ".join(body["limitations"])
    assert "WINDFOR startTime interval semantics" in joined
    assert "same generation population" in joined


def test_summary_has_exactly_the_documented_sections(client: TestClient) -> None:
    body = client.get("/api/analysis/summary").json()

    assert set(body) == {
        "generated_at",
        "analysis_window",
        "cutoff_assumption",
        "period_labelling",
        "counts",
        "metrics",
        "headline_metrics",
        "additional_metrics",
        "lead_time_hours",
        "limitations",
    }


def test_summary_does_not_duplicate_the_audit_lists(client: TestClient) -> None:
    assert "audit" not in client.get("/api/analysis/summary").json()


# --------------------------------------------------------------------------
# /api/analysis/aligned
# --------------------------------------------------------------------------


def test_aligned_returns_bounded_default_page(client: TestClient) -> None:
    response = client.get("/api/analysis/aligned")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 200
    assert body["offset"] == 0
    assert body["count"] == 2
    assert body["hasMore"] is False
    assert [record["targetStart"] for record in body["records"]] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T01:00:00Z",
    ]


def test_aligned_record_has_the_expected_fields(client: TestClient) -> None:
    record = client.get("/api/analysis/aligned").json()["records"][0]

    assert set(record) == {
        "targetStart",
        "actualMW",
        "forecastMW",
        "errorMW",
        "forecastPublishTime",
        "leadHours",
    }
    assert record["errorMW"] == pytest.approx(record["forecastMW"] - record["actualMW"])


def test_aligned_pagination_pages_are_disjoint_and_complete(client: TestClient) -> None:
    first = client.get("/api/analysis/aligned", params={"limit": 1, "offset": 0}).json()
    second = client.get("/api/analysis/aligned", params={"limit": 1, "offset": 1}).json()

    assert first["count"] == 1 and first["hasMore"] is True
    assert second["count"] == 1 and second["hasMore"] is False
    assert first["records"][0]["targetStart"] != second["records"][0]["targetStart"]


def test_aligned_offset_past_the_end_returns_an_honest_empty_page(client: TestClient) -> None:
    body = client.get("/api/analysis/aligned", params={"offset": 99}).json()

    assert body["total"] == 2
    assert body["count"] == 0
    assert body["records"] == []
    assert body["hasMore"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": "many"},
        {"offset": -1},
    ],
)
def test_aligned_rejects_invalid_pagination(client: TestClient, params: dict) -> None:
    assert client.get("/api/analysis/aligned", params=params).status_code == 422


# --------------------------------------------------------------------------
# /api/analysis/report
# --------------------------------------------------------------------------


def test_report_includes_audit_lists_and_definitions(client: TestClient) -> None:
    response = client.get("/api/analysis/report")

    assert response.status_code == 200
    body = response.json()
    assert set(body["audit"]) == {
        "missing_forecast",
        "missing_actual",
        "conflicting_latest_publications",
        "unavailable_hourly_actuals",
    }
    assert body["audit"]["missing_forecast"] == []
    assert body["metric_definitions"]["mape"].startswith("Not used")
    assert body["sources"]["actuals"]["records"] == 4
    assert body["period_labelling"]


def test_report_and_summary_share_the_same_metrics(client: TestClient) -> None:
    summary = client.get("/api/analysis/summary").json()
    report = client.get("/api/analysis/report").json()

    assert summary["metrics"] == report["metrics"]
    assert summary["counts"] == report["counts"]
    assert summary["limitations"] == report["limitations"]


# --------------------------------------------------------------------------
# Missing and broken artefacts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/analysis/summary", "/api/analysis/report"])
def test_missing_report_returns_503_with_clear_code(
    client: TestClient, data_dir: Path, path: str
) -> None:
    (data_dir / REPORT_FILENAME).unlink()

    response = client.get(path)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_data_missing"
    assert REPORT_FILENAME in detail["message"]
    assert "analyse_january_data.py" in detail["message"]


def test_missing_aligned_file_returns_503(client: TestClient, data_dir: Path) -> None:
    (data_dir / ALIGNED_FILENAME).unlink()

    response = client.get("/api/analysis/aligned")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "analysis_data_missing"


def test_error_message_does_not_leak_the_server_path(client: TestClient, data_dir: Path) -> None:
    (data_dir / REPORT_FILENAME).unlink()

    message = client.get("/api/analysis/summary").json()["detail"]["message"]

    assert str(data_dir) not in message
    assert "backend/data/processed" in message


def test_corrupt_report_json_returns_500(client: TestClient, data_dir: Path) -> None:
    (data_dir / REPORT_FILENAME).write_text("{ not json", encoding="utf-8")

    response = client.get("/api/analysis/summary")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_data_invalid"
    assert "not valid JSON" in detail["message"]


def test_report_missing_a_section_returns_500(client: TestClient, data_dir: Path) -> None:
    report = make_report()
    del report["metrics"]
    write_json(data_dir, REPORT_FILENAME, report)

    response = client.get("/api/analysis/summary")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_data_invalid"
    assert "metrics" in detail["message"]


def test_self_contradictory_report_returns_500(client: TestClient, data_dir: Path) -> None:
    report = make_report()
    report["metrics"]["pair_count"] = 3  # counts still say 2
    write_json(data_dir, REPORT_FILENAME, report)

    response = client.get("/api/analysis/summary")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "analysis_data_invalid"


def test_zero_pair_metrics_cannot_be_reported_as_zero(client: TestClient, data_dir: Path) -> None:
    """An empty analysis must expose nulls, not a fabricated 0.0 MAE."""
    report = make_report()
    report["metrics"] = {
        "pair_count": 0,
        "mae_mw": 0.0,
        "rmse_mw": 0.0,
        "bias_mw": 0.0,
        "nmae_percent": 0.0,
        "mean_actual_mw": 0.0,
        "mean_forecast_mw": 0.0,
        "note": None,
    }
    write_json(data_dir, REPORT_FILENAME, report)

    response = client.get("/api/analysis/summary")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "analysis_data_invalid"


def test_corrupt_aligned_record_returns_500(client: TestClient, data_dir: Path) -> None:
    aligned = make_aligned()
    aligned["records"][0]["errorMW"] = 999.0
    write_json(data_dir, ALIGNED_FILENAME, aligned)

    response = client.get("/api/analysis/aligned")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_data_invalid"
    assert "errorMW" in detail["message"]


def test_aligned_file_disagreeing_with_report_returns_500(
    client: TestClient, data_dir: Path
) -> None:
    aligned = make_aligned()
    aligned["records"].append(
        {
            "targetStart": "2026-01-01T02:00:00Z",
            "actualMW": 300.0,
            "forecastMW": 300.0,
            "errorMW": 0.0,
            "forecastPublishTime": "2025-12-31T23:00:00Z",
            "leadHours": 3.0,
        }
    )
    aligned["pair_count"] = 3
    write_json(data_dir, ALIGNED_FILENAME, aligned)

    response = client.get("/api/analysis/aligned")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_data_invalid"
    assert "inconsistent" in detail["message"]


# --------------------------------------------------------------------------
# Real generated artefacts (skipped when the outputs are absent)
# --------------------------------------------------------------------------


@pytest.fixture
def real_client():
    if not (REAL_DATA_DIR / REPORT_FILENAME).is_file():
        pytest.skip("real analysis report is not present")
    if not (REAL_DATA_DIR / ALIGNED_FILENAME).is_file():
        pytest.skip("real aligned analysis is not present")

    app.dependency_overrides[get_analysis_store] = lambda: AnalysisStore(REAL_DATA_DIR)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _load_real(filename: str) -> dict:
    with (REAL_DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_real_summary_matches_the_generated_report(real_client: TestClient) -> None:
    report = _load_real(REPORT_FILENAME)

    body = real_client.get("/api/analysis/summary").json()

    assert body["generated_at"] == report["generated_at"]
    assert body["analysis_window"] == report["analysis_window"]
    assert body["cutoff_assumption"] == report["cutoff_assumption"]
    assert body["counts"] == report["counts"]
    assert body["metrics"] == report["metrics"]
    assert body["lead_time_hours"] == report["lead_time_hours"]
    assert body["limitations"] == report["limitations"]


def test_real_aligned_total_matches_the_report(real_client: TestClient) -> None:
    report = _load_real(REPORT_FILENAME)

    body = real_client.get("/api/analysis/aligned", params={"limit": 5}).json()

    assert body["total"] == report["counts"]["valid_aligned_pairs"]
    assert body["count"] == 5
    assert body["hasMore"] is True
    assert len(body["records"]) == 5


def test_real_aligned_pages_cover_every_record_exactly_once(real_client: TestClient) -> None:
    expected = _load_real(ALIGNED_FILENAME)["records"]

    collected: list[dict] = []
    offset = 0
    page_size = 500
    while True:
        page = real_client.get(
            "/api/analysis/aligned", params={"limit": page_size, "offset": offset}
        ).json()
        collected.extend(page["records"])
        if not page["hasMore"]:
            break
        offset += page["count"]

    assert len(collected) == len(expected)
    assert [record["targetStart"] for record in collected] == [
        record["targetStart"] for record in expected
    ]


def test_real_report_exposes_the_audit_section(real_client: TestClient) -> None:
    report = _load_real(REPORT_FILENAME)

    body = real_client.get("/api/analysis/report").json()

    assert body["audit"] == report["audit"]
    assert body["sources"] == report["sources"]
    assert body["metric_definitions"] == report["metric_definitions"]


# --------------------------------------------------------------------------
# Existing behaviour
# --------------------------------------------------------------------------


def test_health_is_unchanged(client: TestClient) -> None:
    body = client.get("/api/health").json()

    assert set(body) == {"status", "service", "version", "timestamp"}
    assert body["status"] == "ok"


def test_unknown_analysis_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/analysis/unknown").status_code == 404
