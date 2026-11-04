"""Tests for hourly aggregation, alignment and metric formulas.

All fixtures are small synthetic examples written for these tests. They are not
API data and are never used outside the test suite.
"""

from __future__ import annotations

import pytest

from app.services.analysis import (
    AlignedPair,
    align,
    build_hourly_actuals,
    compute_headline_metrics,
    compute_extended_metrics,
    compute_metrics,
    hour_starts,
)
from app.services.data_validation import parse_utc
from app.services.forecast_selection import ForecastVersion, select_forecast


def record(start: str, generation: float) -> dict:
    return {"startTime": start, "generation": generation}


def selection_for(target: str, publish: str, generation: float):
    target_dt = parse_utc(target)
    return select_forecast(
        target_dt,
        [ForecastVersion(target=target_dt, publish=parse_utc(publish), generation=generation)],
    )


START = parse_utc("2026-01-01T00:00:00Z")
END = parse_utc("2026-01-01T03:00:00Z")


# --------------------------------------------------------------------------
# Hourly aggregation
# --------------------------------------------------------------------------


def test_two_half_hours_are_averaged() -> None:
    records = [
        record("2026-01-01T00:00:00Z", 1000),
        record("2026-01-01T00:30:00Z", 2000),
    ]

    hourly, summary = build_hourly_actuals(records, START, START.replace(hour=1))

    assert len(hourly) == 1
    assert hourly[0].generation == pytest.approx(1500.0)
    assert hourly[0].source_starts == (
        parse_utc("2026-01-01T00:00:00Z"),
        parse_utc("2026-01-01T00:30:00Z"),
    )
    assert summary["valid_hours"] == 1
    assert summary["unavailable_hours"] == 0


def test_missing_second_half_hour_prevents_aggregation() -> None:
    records = [record("2026-01-01T00:00:00Z", 1000)]

    hourly, summary = build_hourly_actuals(records, START, START.replace(hour=1))

    assert hourly == []
    assert summary["unavailable_hours"] == 1
    assert "00:30" in summary["unavailable"][0]["reason"]


def test_missing_first_half_hour_prevents_aggregation() -> None:
    records = [record("2026-01-01T00:30:00Z", 2000)]

    hourly, summary = build_hourly_actuals(records, START, START.replace(hour=1))

    assert hourly == []
    assert summary["unavailable_hours"] == 1


def test_non_finite_actual_is_not_averaged() -> None:
    records = [
        record("2026-01-01T00:00:00Z", float("nan")),
        record("2026-01-01T00:30:00Z", 2000),
    ]

    hourly, _ = build_hourly_actuals(records, START, START.replace(hour=1))

    assert hourly == []


def test_hour_starts_covers_the_window_exclusively() -> None:
    hours = hour_starts(START, END)

    assert len(hours) == 3
    assert hours[0] == START
    assert hours[-1] == parse_utc("2026-01-01T02:00:00Z")


# --------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------


def test_alignment_matches_by_target_interval_not_row_order() -> None:
    records = [
        record("2026-01-01T00:00:00Z", 100),
        record("2026-01-01T00:30:00Z", 100),
        record("2026-01-01T01:00:00Z", 200),
        record("2026-01-01T01:30:00Z", 200),
    ]
    hourly, _ = build_hourly_actuals(records, START, START.replace(hour=2))

    selections = [
        selection_for("2026-01-01T01:00:00Z", "2025-12-31T09:00:00Z", 190.0),
        selection_for("2026-01-01T00:00:00Z", "2025-12-31T09:00:00Z", 110.0),
    ]

    pairs, audit = align(list(reversed(hourly)), selections)

    assert [p.target for p in pairs] == [
        parse_utc("2026-01-01T00:00:00Z"),
        parse_utc("2026-01-01T01:00:00Z"),
    ]
    assert [p.actual_mw for p in pairs] == [100.0, 200.0]
    assert [p.forecast_mw for p in pairs] == [110.0, 190.0]
    assert audit["unmatched_targets"] == 0


def test_missing_forecast_is_reported_not_dropped_silently() -> None:
    records = [
        record("2026-01-01T00:00:00Z", 100),
        record("2026-01-01T00:30:00Z", 100),
    ]
    hourly, _ = build_hourly_actuals(records, START, START.replace(hour=1))

    # Forecast published after the cutoff -> not eligible.
    selections = [selection_for("2026-01-01T00:00:00Z", "2026-01-01T05:00:00Z", 120.0)]

    pairs, audit = align(hourly, selections)

    assert pairs == []
    assert len(audit["missing_forecast"]) == 1
    assert audit["unmatched_targets"] == 1


def test_missing_actual_is_reported_for_a_selected_forecast() -> None:
    hourly: list = []
    selections = [selection_for("2026-01-01T00:00:00Z", "2025-12-31T09:00:00Z", 120.0)]

    pairs, audit = align(hourly, selections)

    assert pairs == []
    assert len(audit["missing_actual"]) == 1


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def pair(target: str, actual: float, forecast: float) -> AlignedPair:
    return AlignedPair(
        target=parse_utc(target),
        actual_mw=actual,
        forecast_mw=forecast,
        publish=parse_utc("2025-12-31T22:30:00Z"),
        lead_hours=1.5,
    )


def test_metric_formulas_are_correct() -> None:
    pairs = [
        pair("2026-01-01T00:00:00Z", 100.0, 110.0),  # error  +10
        pair("2026-01-01T01:00:00Z", 200.0, 180.0),  # error  -20
    ]

    metrics = compute_metrics(pairs)

    assert metrics["pair_count"] == 2
    assert metrics["mae_mw"] == pytest.approx(15.0)
    assert metrics["rmse_mw"] == pytest.approx(15.811, abs=1e-3)
    assert metrics["bias_mw"] == pytest.approx(-5.0)
    assert metrics["mean_actual_mw"] == pytest.approx(150.0)
    assert metrics["mean_forecast_mw"] == pytest.approx(145.0)
    assert metrics["nmae_percent"] == pytest.approx(10.0)


def test_bias_sign_is_forecast_minus_actual() -> None:
    metrics = compute_metrics([pair("2026-01-01T00:00:00Z", 100.0, 130.0)])

    assert metrics["bias_mw"] == pytest.approx(30.0)
    assert metrics["mae_mw"] == pytest.approx(30.0)


def test_empty_pairs_give_unavailable_metrics_not_zero() -> None:
    metrics = compute_metrics([])

    assert metrics["pair_count"] == 0
    assert metrics["mae_mw"] is None
    assert metrics["rmse_mw"] is None
    assert metrics["bias_mw"] is None
    assert metrics["nmae_percent"] is None
    assert "unavailable" in metrics["note"].lower()


def test_nmae_is_unavailable_when_mean_actual_is_zero() -> None:
    metrics = compute_metrics([pair("2026-01-01T00:00:00Z", 0.0, 25.0)])

    assert metrics["pair_count"] == 1
    assert metrics["mae_mw"] == pytest.approx(25.0)
    assert metrics["nmae_percent"] is None
    assert "not strictly positive" in metrics["note"]


def test_nmae_is_unavailable_when_mean_actual_is_negative() -> None:
    metrics = compute_metrics([pair("2026-01-01T00:00:00Z", -10.0, 25.0)])

    assert metrics["nmae_percent"] is None


def test_headline_metrics_report_overforecast_share_and_bias_removed_rmse() -> None:
    headline = compute_headline_metrics(
        [
            pair("2026-01-01T00:00:00Z", 100.0, 110.0),
            pair("2026-01-01T01:00:00Z", 200.0, 180.0),
        ]
    )

    assert headline["overforecast_share_percent"] == pytest.approx(50.0)
    assert headline["rmse_after_bias_mw"] == pytest.approx(15.0)
    assert headline["bias_squared_error_share_percent"] == pytest.approx(10.0)
    assert headline["bias_percent_of_mean_actual"] == pytest.approx(-3.3333)
    assert "15 MW" in headline["headline_text"]
    assert "50.0% of hours" in headline["headline_text"]


def test_headline_metrics_return_unavailable_fields_for_empty_pairs() -> None:
    headline = compute_headline_metrics([])

    assert headline["overforecast_share_percent"] is None
    assert headline["rmse_after_bias_mw"] is None
    assert headline["bias_squared_error_share_percent"] is None
    assert headline["bias_percent_of_mean_actual"] is None
    assert "No aligned pairs" in headline["headline_text"]


def test_headline_metrics_handle_zero_rmse_without_dividing_by_zero() -> None:
    headline = compute_headline_metrics(
        [pair("2026-01-01T00:00:00Z", 100.0, 100.0)]
    )

    assert headline["overforecast_share_percent"] == 0.0
    assert headline["rmse_after_bias_mw"] == 0.0
    assert headline["bias_squared_error_share_percent"] == 0.0


def test_extended_metrics_cover_percentiles_groups_baseline_and_sensitivity() -> None:
    pairs = [
        pair("2026-01-01T00:00:00Z", 100.0, 110.0),
        pair("2026-01-01T01:00:00Z", 200.0, 180.0),
    ]
    hourly_actuals, _ = build_hourly_actuals(
        [
            record("2025-12-31T00:00:00Z", 50.0),
            record("2025-12-31T00:30:00Z", 50.0),
            record("2025-12-31T01:00:00Z", 100.0),
            record("2025-12-31T01:30:00Z", 100.0),
            record("2026-01-01T00:00:00Z", 100.0),
            record("2026-01-01T00:30:00Z", 100.0),
            record("2026-01-01T01:00:00Z", 200.0),
            record("2026-01-01T01:30:00Z", 200.0),
        ],
        parse_utc("2025-12-31T00:00:00Z"),
        parse_utc("2026-01-01T02:00:00Z"),
    )

    result = compute_extended_metrics(pairs, hourly_actuals)

    assert result["p90_absolute_error_mw"] == pytest.approx(19.0)
    assert result["p95_absolute_error_mw"] == pytest.approx(19.5)
    assert result["largest_miss"] == {
        "target_start": "2026-01-01T01:00:00Z",
        "date_utc": "2026-01-01",
        "hour_utc": 1,
        "absolute_error_mw": 20.0,
        "error_mw": -20.0,
        "actual_mw": 200.0,
        "forecast_mw": 180.0,
    }
    assert result["naive_previous_day_baseline"] == {
        "pair_count": 2,
        "mae_mw": 75.0,
        "rmse_mw": pytest.approx(79.0569, abs=0.001),
    }
    assert result["mae_reduction_vs_naive_percent"] == 80.0
    assert result["by_lead_time_bucket"][0] == {
        "bucket": "<6h",
        "pair_count": 2,
        "mae_mw": 15.0,
        "bias_mw": -5.0,
    }
    assert result["by_hour_of_day"][0]["mae_mw"] == 10.0
    assert result["by_hour_of_day"][1]["bias_mw"] == -20.0
    assert result["hour_of_day_mae_extremes"] == {
        "highest_hour_utc": 1,
        "highest_mae_mw": 20.0,
        "lowest_hour_utc": 0,
        "lowest_mae_mw": 10.0,
    }
    assert result["worst_days_by_mae"] == [
        {"date_utc": "2026-01-01", "pair_count": 2, "mae_mw": 15.0}
    ]
    assert result["timestamp_sensitivity"] == [
        {"shift_hours": -1, "pair_count": 1, "mae_mw": 90.0, "bias_mw": -90.0},
        {"shift_hours": 0, "pair_count": 2, "mae_mw": 15.0, "bias_mw": -5.0},
        {"shift_hours": 1, "pair_count": 1, "mae_mw": 80.0, "bias_mw": 80.0},
    ]


def test_extended_metrics_return_empty_states_for_no_pairs() -> None:
    result = compute_extended_metrics([], [])

    assert result["p90_absolute_error_mw"] is None
    assert result["p95_absolute_error_mw"] is None
    assert result["largest_miss"] is None
    assert result["scatter_peak_caption"] is None
    assert result["naive_previous_day_baseline"] == {
        "pair_count": 0,
        "mae_mw": None,
        "rmse_mw": None,
    }
    assert result["mae_reduction_vs_naive_percent"] is None
    assert all(row["pair_count"] == 0 for row in result["by_lead_time_bucket"])
    assert len(result["by_hour_of_day"]) == 24
    assert result["hour_of_day_mae_extremes"] == {
        "highest_hour_utc": None,
        "highest_mae_mw": None,
        "lowest_hour_utc": None,
        "lowest_mae_mw": None,
    }
    assert result["worst_days_by_mae"] == []
    assert [row["pair_count"] for row in result["timestamp_sensitivity"]] == [0, 0, 0]


def test_scatter_peak_caption_is_rounded_from_aligned_pairs() -> None:
    pairs = [pair("2026-01-01T00:00:00Z", 17_755.5, 21_064.0)]

    result = compute_extended_metrics(pairs, [])

    assert result["scatter_peak_caption"] == (
        "Forecast peaks reach about 20 GW while actuals top out near 17.5 GW."
    )


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_repeated_analysis_produces_equivalent_results() -> None:
    records = [
        record("2026-01-01T00:00:00Z", 100),
        record("2026-01-01T00:30:00Z", 200),
        record("2026-01-01T01:00:00Z", 300),
        record("2026-01-01T01:30:00Z", 400),
    ]
    selections = [
        selection_for("2026-01-01T00:00:00Z", "2025-12-31T22:30:00Z", 150.0),
        selection_for("2026-01-01T01:00:00Z", "2025-12-31T22:30:00Z", 360.0),
    ]

    def run(records_in, selections_in):
        hourly, summary = build_hourly_actuals(records_in, START, START.replace(hour=2))
        pairs, audit = align(hourly, selections_in)
        return summary, [(p.target, p.actual_mw, p.forecast_mw) for p in pairs], compute_metrics(pairs)

    first = run(records, selections)
    second = run(list(reversed(records)), list(reversed(selections)))
    third = run(records, selections)

    assert first == second == third
