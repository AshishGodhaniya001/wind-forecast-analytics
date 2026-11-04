"""Tests for validation, normalisation and target-period filtering.

Every record in this file is a small hand-written example used only to exercise
code paths. These are **not** real API responses and must never be presented as
data or results.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.data_validation import (
    coerce_generation,
    filter_target_window,
    parse_utc,
    to_iso_z,
    validate_actuals,
    validate_forecasts,
)

UTC = timezone.utc


# --------------------------------------------------------------------------
# Synthetic fixtures (test-only)
# --------------------------------------------------------------------------


def actual(
    start: str,
    generation: object,
    publish: str | None = None,
    **overrides: object,
) -> dict:
    record = {
        "dataset": "FUELHH",
        "publishTime": publish,
        "startTime": start,
        "settlementDate": start[:10] if isinstance(start, str) else None,
        "settlementPeriod": 1,
        "fuelType": "WIND",
        "generation": generation,
    }
    record.update(overrides)
    return record


def forecast(start: str, publish: str, generation: object, **overrides: object) -> dict:
    record = {
        "dataset": "WINDFOR",
        "publishTime": publish,
        "startTime": start,
        "generation": generation,
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# Timestamp handling
# --------------------------------------------------------------------------


def test_parse_utc_accepts_z_suffix() -> None:
    parsed = parse_utc("2026-01-01T00:30:00Z")

    assert parsed == datetime(2026, 1, 1, 0, 30, tzinfo=UTC)
    assert parsed.utcoffset().total_seconds() == 0


def test_parse_utc_normalises_other_offsets_to_utc() -> None:
    parsed = parse_utc("2026-01-01T01:00:00+01:00")

    assert parsed == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert to_iso_z(parsed) == "2026-01-01T00:00:00Z"


def test_parse_utc_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="no timezone offset"):
        parse_utc("2026-01-01T00:00:00")


def test_parse_utc_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid ISO-8601"):
        parse_utc("not-a-timestamp")


def test_coerce_generation_accepts_numbers_and_numeric_strings() -> None:
    assert coerce_generation(14077) == 14077.0
    assert coerce_generation(14077.5) == 14077.5
    assert coerce_generation(" 14077 ") == 14077.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_coerce_generation_rejects_non_finite(value: float) -> None:
    with pytest.raises(ValueError, match="not finite"):
        coerce_generation(value)


def test_coerce_generation_rejects_boolean() -> None:
    with pytest.raises(ValueError, match="boolean"):
        coerce_generation(True)


# --------------------------------------------------------------------------
# Actuals
# --------------------------------------------------------------------------


def test_valid_actuals_are_normalised_and_sorted() -> None:
    records = [
        actual("2026-01-01T00:30:00Z", 14036, "2026-01-01T01:00:00Z"),
        actual("2026-01-01T00:00:00Z", 13756, "2026-01-01T00:30:00Z"),
    ]

    rows, report = validate_actuals(records)

    assert [row["startTime"] for row in rows] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:30:00Z",
    ]
    assert rows[0]["generation"] == 13756.0
    assert rows[0]["publishTime"] == "2026-01-01T00:30:00Z"
    assert rows[0]["fuelType"] == "WIND"
    assert report.valid_rows == 2
    assert report.rejected_rows == 0
    assert report.distinct_targets == 2
    assert report.resolution_seconds == 1800


def test_missing_generation_is_rejected_and_counted() -> None:
    record = actual("2026-01-01T00:00:00Z", 1)
    del record["generation"]

    rows, report = validate_actuals([record])

    assert rows == []
    assert report.rejected_rows == 1
    assert report.missing_field_rows == 1
    assert "generation" in report.rejected[0].reason


def test_null_start_time_is_rejected() -> None:
    rows, report = validate_actuals([actual(None, 100)])

    assert rows == []
    assert report.rejected_rows == 1
    assert report.missing_field_rows == 1


def test_invalid_start_time_is_rejected() -> None:
    rows, report = validate_actuals([actual("01/01/2026 00:00", 100)])

    assert rows == []
    assert report.invalid_value_rows == 1


def test_naive_start_time_is_rejected_not_assumed_utc() -> None:
    rows, report = validate_actuals([actual("2026-01-01T00:00:00", 100)])

    assert rows == []
    assert report.invalid_value_rows == 1
    assert "timezone" in report.rejected[0].reason


def test_non_finite_generation_is_counted_separately() -> None:
    rows, report = validate_actuals([actual("2026-01-01T00:00:00Z", float("nan"))])

    assert rows == []
    assert report.non_finite_rows == 1


def test_wrong_fuel_type_is_rejected() -> None:
    rows, report = validate_actuals(
        [actual("2026-01-01T00:00:00Z", 100, fuelType="NUCLEAR")]
    )

    assert rows == []
    assert report.invalid_value_rows == 1
    assert "WIND" in report.rejected[0].reason


def test_non_object_record_is_rejected_without_crashing() -> None:
    rows, report = validate_actuals(["not-a-record", 42, None])  # type: ignore[list-item]

    assert rows == []
    assert report.rejected_rows == 3


def test_exact_duplicate_actuals_are_counted_not_silently_dropped() -> None:
    record = actual("2026-01-01T00:00:00Z", 13756, "2026-01-01T00:30:00Z")

    rows, report = validate_actuals([record, dict(record)])

    assert len(rows) == 1
    assert report.exact_duplicates == 1
    assert len(report.duplicates) == 1


def test_conflicting_actuals_keep_latest_publication() -> None:
    records = [
        actual("2026-01-01T00:00:00Z", 1000, "2026-01-01T00:30:00Z"),
        actual("2026-01-01T00:00:00Z", 1200, "2026-01-01T02:00:00Z"),
    ]

    rows, report = validate_actuals(records)

    assert len(rows) == 1
    assert rows[0]["generation"] == 1200.0
    assert report.conflicting_records == 1
    assert len(report.conflicts) == 1


# --------------------------------------------------------------------------
# Target-period filtering
# --------------------------------------------------------------------------


def test_target_window_is_half_open_and_drops_boundary_records() -> None:
    records = [
        actual("2025-12-31T23:30:00Z", 1, "2026-01-01T00:00:00Z"),
        actual("2026-01-01T00:00:00Z", 2, "2026-01-01T00:30:00Z"),
        actual("2026-01-31T23:30:00Z", 3, "2026-02-01T00:00:00Z"),
        actual("2026-02-01T00:00:00Z", 4, "2026-02-01T00:30:00Z"),
    ]

    rows, report = validate_actuals(
        records,
        target_start=parse_utc("2026-01-01T00:00:00Z"),
        target_end=parse_utc("2026-02-01T00:00:00Z"),
    )

    assert [row["startTime"] for row in rows] == [
        "2026-01-01T00:00:00Z",
        "2026-01-31T23:30:00Z",
    ]
    assert report.target_rows_outside_window == 2
    assert report.outside_window_min_start == datetime(2025, 12, 31, 23, 30, tzinfo=UTC)
    assert report.outside_window_max_start == datetime(2026, 2, 1, 0, 0, tzinfo=UTC)


def test_filter_target_window_returns_kept_and_dropped() -> None:
    records = [
        {"startTime": "2025-12-31T23:30:00Z", "generation": 1.0},
        {"startTime": "2026-01-01T00:00:00Z", "generation": 2.0},
    ]

    kept, dropped = filter_target_window(
        records,
        parse_utc("2026-01-01T00:00:00Z"),
        parse_utc("2026-02-01T00:00:00Z"),
    )

    assert len(kept) == 1
    assert len(dropped) == 1
    assert dropped[0]["startTime"] == "2025-12-31T23:30:00Z"


# --------------------------------------------------------------------------
# Forecasts
# --------------------------------------------------------------------------


def test_multiple_forecast_versions_for_one_target_are_preserved() -> None:
    records = [
        forecast("2026-01-01T12:00:00Z", "2025-12-31T02:30:00Z", 19000),
        forecast("2026-01-01T12:00:00Z", "2025-12-31T11:30:00Z", 19500),
        forecast("2026-01-01T12:00:00Z", "2025-12-31T22:30:00Z", 19800),
    ]

    rows, report = validate_forecasts(records)

    assert len(rows) == 3
    assert report.distinct_targets == 1
    assert report.versions_per_target_min == 3
    assert report.versions_per_target_max == 3
    assert [row["publishTime"] for row in rows] == [
        "2025-12-31T02:30:00Z",
        "2025-12-31T11:30:00Z",
        "2025-12-31T22:30:00Z",
    ]


def test_forecast_requires_publish_time() -> None:
    record = forecast("2026-01-01T12:00:00Z", "2025-12-31T02:30:00Z", 19000)
    del record["publishTime"]

    rows, report = validate_forecasts([record])

    assert rows == []
    assert report.missing_field_rows == 1


def test_forecast_duplicate_same_start_and_publish_is_deduped() -> None:
    record = forecast("2026-01-01T12:00:00Z", "2025-12-31T02:30:00Z", 19000)

    rows, report = validate_forecasts([record, dict(record)])

    assert len(rows) == 1
    assert report.exact_duplicates == 1


def test_forecast_resolution_is_measured_not_assumed() -> None:
    records = [
        forecast("2026-01-01T00:00:00Z", "2025-12-31T02:30:00Z", 1),
        forecast("2026-01-01T01:00:00Z", "2025-12-31T02:30:00Z", 2),
        forecast("2026-01-01T02:00:00Z", "2025-12-31T02:30:00Z", 3),
    ]

    _, report = validate_forecasts(records)

    assert report.resolution_seconds == 3600
    assert report.irregular_gap_count == 0


def test_gap_in_series_is_reported_as_irregular() -> None:
    records = [
        actual("2026-01-01T00:00:00Z", 1),
        actual("2026-01-01T00:30:00Z", 2),
        actual("2026-01-01T02:00:00Z", 3),
    ]

    _, report = validate_actuals(records)

    assert report.resolution_seconds == 1800
    assert report.irregular_gap_count == 1
    assert any("possible missing periods" in warning for warning in report.warnings)


def test_report_serialises_to_json_safe_dict() -> None:
    rows, report = validate_actuals([actual("2026-01-01T00:00:00Z", 1, "2026-01-01T00:30:00Z")])

    payload = report.as_dict()

    assert payload["dataset"] == "FUELHH"
    assert payload["min_start_time"] == "2026-01-01T00:00:00Z"
    assert isinstance(payload["resolution_counts"], dict)
    assert rows[0]["startTime"] == "2026-01-01T00:00:00Z"
