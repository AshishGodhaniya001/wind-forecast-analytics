"""Aggregate half-hourly actuals to hourly values, align, and score.

Period labelling
----------------
``startTime`` is treated as the **start** of the interval it describes, for both
datasets:

* FUELHH: the stored data shows ``settlementPeriod`` 1 at ``00:00`` and 48 at
  ``23:30``, and each value is published at ``startTime + 30 min``. A value
  therefore covers ``[startTime, startTime + 30 min)``.
* WINDFOR: the challenge brief describes its ``startTime`` as "similar to the
  startTime field in the actuals dataset", so an hourly value is taken to cover
  ``[startTime, startTime + 1 h)``.

An hourly actual is therefore the mean of the two half-hour values that start
at ``H`` and ``H + 30 min``. No timestamp is shifted anywhere.

Metrics
-------
``error = forecast - actual`` (MW). Positive bias means forecasts ran high.
MAE and RMSE are in MW, bias is in MW, nMAE is a percentage of mean actual.
MAPE is deliberately not used: January contains low-generation hours where a
percentage of actual would explode.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from app.services.data_validation import parse_utc
from app.services.forecast_selection import Selection

HALF_HOUR = timedelta(minutes=30)
ONE_HOUR = timedelta(hours=1)
ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class HourlyActual:
    target: datetime
    generation: float
    source_starts: tuple[datetime, datetime]


@dataclass(frozen=True)
class AlignedPair:
    target: datetime
    actual_mw: float
    forecast_mw: float
    publish: datetime
    lead_hours: float

    @property
    def error_mw(self) -> float:
        return self.forecast_mw - self.actual_mw


def hour_starts(start: datetime, end: datetime) -> list[datetime]:
    """Every whole hour from ``start`` up to (excluding) ``end``."""
    if end <= start:
        raise ValueError("end must be later than start")
    hours: list[datetime] = []
    cursor = start
    while cursor < end:
        hours.append(cursor)
        cursor += ONE_HOUR
    return hours


def build_hourly_actuals(
    records: Iterable[Mapping[str, object]],
    target_start: datetime,
    target_end: datetime,
) -> tuple[list[HourlyActual], dict]:
    """Average each pair of half-hour actuals into one hourly value.

    An hour is only produced when **both** half-hours are present and finite.
    A partial hour is never averaged.
    """
    by_start: dict[datetime, float] = {}
    for record in records:
        start = parse_utc(record["startTime"])
        value = record["generation"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        number = float(value)
        if math.isfinite(number):
            by_start[start] = number

    hourly: list[HourlyActual] = []
    unavailable: list[dict] = []

    for start in hour_starts(target_start, target_end):
        first = by_start.get(start)
        second = by_start.get(start + HALF_HOUR)

        if first is None or second is None:
            missing = [
                (start + offset).strftime("%Y-%m-%dT%H:%M:%SZ")
                for offset, value in ((timedelta(0), first), (HALF_HOUR, second))
                if value is None
            ]
            unavailable.append(
                {
                    "targetStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "missing half-hour actual(s): " + ", ".join(missing),
                }
            )
            continue

        hourly.append(
            HourlyActual(
                target=start,
                generation=(first + second) / 2.0,
                source_starts=(start, start + HALF_HOUR),
            )
        )

    expected = len(hour_starts(target_start, target_end))
    summary = {
        "source_records": len(by_start),
        "expected_hours": expected,
        "valid_hours": len(hourly),
        "unavailable_hours": len(unavailable),
        "unavailable": unavailable,
    }
    return hourly, summary


def align(
    hourly_actuals: Sequence[HourlyActual],
    selections: Sequence[Selection],
) -> tuple[list[AlignedPair], dict]:
    """Join actuals and selected forecasts strictly by target interval."""
    actual_by_target = {row.target: row for row in hourly_actuals}

    pairs: list[AlignedPair] = []
    missing_actual: list[dict] = []
    missing_forecast: list[dict] = []
    conflicts: list[dict] = []

    selected_targets = set()

    for selection in selections:
        selected_targets.add(selection.target)

        if selection.status == "conflict":
            conflicts.append(
                {
                    "targetStart": selection.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "multiple different values at the latest eligible publishTime",
                    "publishTime": sorted(
                        {v.publish.strftime("%Y-%m-%dT%H:%M:%SZ") for v in selection.conflicting}
                    ),
                    "values": sorted({v.generation for v in selection.conflicting}),
                }
            )
            continue

        if not selection.is_usable:
            missing_forecast.append(
                {
                    "targetStart": selection.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "no forecast published before the cutoff",
                    "cutoff": selection.cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "available_versions": selection.available_count,
                }
            )
            continue

        actual = actual_by_target.get(selection.target)
        if actual is None:
            missing_actual.append(
                {
                    "targetStart": selection.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "no valid hourly actual (both half-hours required)",
                }
            )
            continue

        assert selection.version is not None
        pairs.append(
            AlignedPair(
                target=selection.target,
                actual_mw=actual.generation,
                forecast_mw=selection.version.generation,
                publish=selection.version.publish,
                lead_hours=selection.lead_hours or 0.0,
            )
        )

    # Hours that have an actual but no selection at all (target outside the
    # forecast selection list) are also unmatched, and must stay visible.
    for row in hourly_actuals:
        if row.target not in selected_targets:
            missing_forecast.append(
                {
                    "targetStart": row.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "target not present in the forecast dataset",
                }
            )

    pairs.sort(key=lambda pair: pair.target)

    audit = {
        "aligned_pairs": len(pairs),
        "missing_forecast": missing_forecast,
        "missing_actual": missing_actual,
        "conflicting_latest_publications": conflicts,
        "unmatched_targets": len(missing_forecast) + len(missing_actual) + len(conflicts),
    }
    return pairs, audit


def compute_metrics(pairs: Sequence[AlignedPair]) -> dict:
    """MAE, RMSE, Bias and nMAE over valid aligned pairs only."""
    count = len(pairs)
    if count == 0:
        return {
            "pair_count": 0,
            "mae_mw": None,
            "rmse_mw": None,
            "bias_mw": None,
            "nmae_percent": None,
            "mean_actual_mw": None,
            "mean_forecast_mw": None,
            "note": "No valid aligned pairs - metrics are unavailable, not zero.",
        }

    errors = [pair.error_mw for pair in pairs]
    mean_actual = sum(pair.actual_mw for pair in pairs) / count
    mean_forecast = sum(pair.forecast_mw for pair in pairs) / count

    mae = sum(abs(e) for e in errors) / count
    rmse = math.sqrt(sum(e * e for e in errors) / count)
    bias = sum(errors) / count

    # nMAE is only meaningful when the actual generation level is positive.
    nmae = (mae / mean_actual * 100.0) if mean_actual > 0 else None

    return {
        "pair_count": count,
        "mae_mw": round(mae, 3),
        "rmse_mw": round(rmse, 3),
        "bias_mw": round(bias, 3),
        "nmae_percent": round(nmae, 4) if nmae is not None else None,
        "mean_actual_mw": round(mean_actual, 3),
        "mean_forecast_mw": round(mean_forecast, 3),
        "note": (
            None
            if nmae is not None
            else "nMAE unavailable: mean actual generation is not strictly positive."
        ),
    }


def compute_headline_metrics(pairs: Sequence[AlignedPair]) -> dict:
    """Compute the directional forecast headline and bias-adjusted RMSE.

    The existing MAE, RMSE, bias and nMAE implementation above is intentionally
    unchanged. These additional values are derived independently from aligned
    forecast/actual pairs.
    """
    count = len(pairs)
    if count == 0:
        return {
            "overforecast_share_percent": None,
            "rmse_after_bias_mw": None,
            "bias_squared_error_share_percent": None,
            "bias_percent_of_mean_actual": None,
            "headline_text": "No aligned pairs are available to calculate the headline insight.",
        }

    errors = [pair.error_mw for pair in pairs]
    bias = sum(errors) / count
    rmse = math.sqrt(sum(error * error for error in errors) / count)
    rmse_after_bias = math.sqrt(
        sum((error - bias) ** 2 for error in errors) / count
    )
    mean_actual = sum(pair.actual_mw for pair in pairs) / count
    overforecast_share = sum(error > 0 for error in errors) / count * 100.0
    bias_squared_error_share = (
        bias * bias / (rmse * rmse) * 100.0 if rmse > 0 else 0.0
    )
    bias_percent = bias / mean_actual * 100.0 if mean_actual > 0 else None

    if bias_percent is None:
        headline_text = (
            f"Forecasts ran {abs(bias) / 1000:.2f} GW "
            f"{'above' if bias >= 0 else 'below'} actual; removing bias reduces "
            f"RMSE to {rmse_after_bias:,.0f} MW. Bias accounts for "
            f"{bias_squared_error_share:.1f}% of squared error, and forecast "
            f"exceeded actual in {overforecast_share:.1f}% of hours."
        )
    else:
        headline_text = (
            f"Forecasts ran {abs(bias) / 1000:.2f} GW "
            f"({abs(bias_percent):.1f}% of mean actual) "
            f"{'above' if bias >= 0 else 'below'} actual; removing bias reduces "
            f"RMSE to {rmse_after_bias:,.0f} MW. Bias accounts for "
            f"{bias_squared_error_share:.1f}% of squared error, and forecast "
            f"exceeded actual in {overforecast_share:.1f}% of hours."
        )

    return {
        "overforecast_share_percent": round(overforecast_share, 4),
        "rmse_after_bias_mw": round(rmse_after_bias, 3),
        "bias_squared_error_share_percent": round(bias_squared_error_share, 4),
        "bias_percent_of_mean_actual": (
            round(bias_percent, 4) if bias_percent is not None else None
        ),
        "headline_text": headline_text,
    }


LEAD_TIME_BUCKETS = (
    ("<6h", 0.0, 6.0),
    ("6-12h", 6.0, 12.0),
    ("12-18h", 12.0, 18.0),
    ("18-24h", 18.0, 24.0),
    ("24-30h", 24.0, 30.0),
    ("30-36h", 30.0, 36.0),
    ("36-40h", 36.0, 40.0),
    (">=40h", 40.0, math.inf),
)


def _linear_quantile(values: Sequence[float], probability: float) -> float | None:
    """Return a linearly interpolated quantile (Hyndman-Fan type 7)."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _error_summary(pairs: Sequence[AlignedPair]) -> dict:
    if not pairs:
        return {"pair_count": 0, "mae_mw": None, "bias_mw": None}
    errors = [pair.error_mw for pair in pairs]
    return {
        "pair_count": len(pairs),
        "mae_mw": round(sum(abs(error) for error in errors) / len(errors), 3),
        "bias_mw": round(sum(errors) / len(errors), 3),
    }


def compute_extended_metrics(
    pairs: Sequence[AlignedPair],
    hourly_actuals: Sequence[HourlyActual],
) -> dict:
    """Compute distributional, baseline, grouping and sensitivity diagnostics.

    ``hourly_actuals`` may include the day before the scoring window so the
    previous-day naive baseline can cover the first delivery day.
    """
    errors = [pair.error_mw for pair in pairs]
    absolute_errors = [abs(error) for error in errors]
    p90 = _linear_quantile(absolute_errors, 0.90)
    p95 = _linear_quantile(absolute_errors, 0.95)

    if pairs:
        largest = min(pairs, key=lambda pair: (-abs(pair.error_mw), pair.target))
        largest_miss = {
            "target_start": largest.target.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_utc": largest.target.date().isoformat(),
            "hour_utc": largest.target.hour,
            "absolute_error_mw": round(abs(largest.error_mw), 3),
            "error_mw": round(largest.error_mw, 3),
            "actual_mw": round(largest.actual_mw, 3),
            "forecast_mw": round(largest.forecast_mw, 3),
        }
    else:
        largest_miss = None

    if pairs:
        # This is an approximate chart caption, not a scored metric. Use coarse
        # GW rounding so it describes the relative peak levels without false precision.
        forecast_peak_about_gw = round(max(pair.forecast_mw for pair in pairs) / 5_000.0) * 5
        actual_peak_near_gw = math.floor(max(pair.actual_mw for pair in pairs) / 500.0) / 2
        scatter_peak_caption = (
            f"Forecast peaks reach about {forecast_peak_about_gw:.0f} GW while actuals "
            f"top out near {actual_peak_near_gw:.1f} GW."
        )
    else:
        scatter_peak_caption = None

    by_lead: dict[str, list[AlignedPair]] = {label: [] for label, _, _ in LEAD_TIME_BUCKETS}
    by_hour: dict[int, list[AlignedPair]] = {hour: [] for hour in range(24)}
    by_day: dict[date, list[AlignedPair]] = defaultdict(list)
    for pair in pairs:
        for label, lower, upper in LEAD_TIME_BUCKETS:
            if lower <= pair.lead_hours < upper:
                by_lead[label].append(pair)
                break
        by_hour[pair.target.hour].append(pair)
        by_day[pair.target.date()].append(pair)

    hourly_actual_by_target = {row.target: row.generation for row in hourly_actuals}
    baseline_pairs: list[tuple[float, float]] = []
    for pair in pairs:
        previous_actual = hourly_actual_by_target.get(pair.target - ONE_DAY)
        if previous_actual is not None:
            baseline_pairs.append((pair.actual_mw, previous_actual))
    baseline_errors = [forecast - actual for actual, forecast in baseline_pairs]
    baseline = {
        "pair_count": len(baseline_pairs),
        "mae_mw": (
            round(sum(abs(error) for error in baseline_errors) / len(baseline_errors), 3)
            if baseline_errors
            else None
        ),
        "rmse_mw": (
            round(math.sqrt(sum(error * error for error in baseline_errors) / len(baseline_errors)), 3)
            if baseline_errors
            else None
        ),
    }
    model_mae = (
        sum(absolute_errors) / len(absolute_errors)
        if absolute_errors
        else None
    )
    mae_reduction_vs_naive_percent = (
        round((baseline["mae_mw"] - model_mae) / baseline["mae_mw"] * 100.0, 3)
        if baseline["mae_mw"] is not None and baseline["mae_mw"] > 0 and model_mae is not None
        else None
    )

    forecast_by_target = {pair.target: pair.forecast_mw for pair in pairs}
    timestamp_sensitivity = []
    for shift_hours in (-1, 0, 1):
        shifted = []
        for pair in pairs:
            shifted_forecast = forecast_by_target.get(pair.target + timedelta(hours=shift_hours))
            if shifted_forecast is not None:
                shifted.append((shifted_forecast - pair.actual_mw, pair.target))
        shifted_errors = [error for error, _ in shifted]
        timestamp_sensitivity.append(
            {
                "shift_hours": shift_hours,
                "pair_count": len(shifted_errors),
                "mae_mw": (
                    round(sum(abs(error) for error in shifted_errors) / len(shifted_errors), 3)
                    if shifted_errors
                    else None
                ),
                "bias_mw": (
                    round(sum(shifted_errors) / len(shifted_errors), 3)
                    if shifted_errors
                    else None
                ),
            }
        )

    worst_days = []
    for day, day_pairs in by_day.items():
        summary = _error_summary(day_pairs)
        worst_days.append(
            {
                "date_utc": day.isoformat(),
                "pair_count": summary["pair_count"],
                "mae_mw": summary["mae_mw"],
            }
        )
    worst_days.sort(key=lambda row: (-row["mae_mw"], row["date_utc"]))

    by_hour_rows = [
        {"hour_utc": hour, **_error_summary(hour_pairs)}
        for hour, hour_pairs in by_hour.items()
    ]
    populated_hours = [row for row in by_hour_rows if row["pair_count"] > 0]
    if populated_hours:
        highest_hour = max(populated_hours, key=lambda row: (row["mae_mw"], -row["hour_utc"]))
        lowest_hour = min(populated_hours, key=lambda row: (row["mae_mw"], row["hour_utc"]))
        hour_of_day_mae_extremes = {
            "highest_hour_utc": highest_hour["hour_utc"],
            "highest_mae_mw": highest_hour["mae_mw"],
            "lowest_hour_utc": lowest_hour["hour_utc"],
            "lowest_mae_mw": lowest_hour["mae_mw"],
        }
    else:
        hour_of_day_mae_extremes = {
            "highest_hour_utc": None,
            "highest_mae_mw": None,
            "lowest_hour_utc": None,
            "lowest_mae_mw": None,
        }

    return {
        "p90_absolute_error_mw": round(p90, 3) if p90 is not None else None,
        "p95_absolute_error_mw": round(p95, 3) if p95 is not None else None,
        "largest_miss": largest_miss,
        "scatter_peak_caption": scatter_peak_caption,
        "naive_previous_day_baseline": baseline,
        "mae_reduction_vs_naive_percent": mae_reduction_vs_naive_percent,
        "by_lead_time_bucket": [
            {"bucket": label, **_error_summary(bucket_pairs)}
            for label, bucket_pairs in by_lead.items()
        ],
        "by_hour_of_day": by_hour_rows,
        "hour_of_day_mae_extremes": hour_of_day_mae_extremes,
        "worst_days_by_mae": worst_days[:5],
        "timestamp_sensitivity": timestamp_sensitivity,
    }
