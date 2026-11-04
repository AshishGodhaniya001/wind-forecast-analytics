"""Run the January 2026 wind forecast accuracy analysis.

Run from the ``backend/`` directory after the Step 3 retrieval:

    python scripts/analyse_january_data.py

Inputs (read-only, never modified)
----------------------------------
``data/processed/actuals_january_2026.json``
``data/processed/forecasts_january_2026.json``

Outputs
-------
``data/processed/hourly_actuals_january_2026.json``
    Half-hourly actuals averaged into hourly values (both half-hours required).
``data/processed/selected_forecasts_january_2026.json``
    The single forecast chosen per delivery target by the cutoff rule, plus the
    targets that had no eligible forecast.
``data/processed/aligned_analysis_january_2026.json``
    Actual/forecast pairs with their signed error.
``data/processed/analysis_report_january_2026.json``
    Counts, metric definitions, results, lead-time distribution and limitations.

No forecast published at or after its cutoff is ever used.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.analysis import (  # noqa: E402
    ONE_HOUR,
    align,
    build_hourly_actuals,
    compute_extended_metrics,
    compute_headline_metrics,
    compute_metrics,
    hour_starts,
)
from app.services.data_validation import parse_utc, to_iso_z  # noqa: E402
from app.services.forecast_selection import (  # noqa: E402
    ForecastVersion,
    delivery_day_cutoff,
    select_forecast,
    summarise_lead_times,
)

DEFAULT_TARGET_START = "2026-01-01T00:00:00Z"
DEFAULT_TARGET_END = "2026-02-01T00:00:00Z"

CUTOFF_RULE = (
    "For delivery day D (Europe/London), the latest forecast whose publishTime "
    "is strictly earlier than 09:20 Europe/London on D-1."
)

PERIOD_LABELLING = (
    "startTime marks the START of the interval it describes. FUELHH: "
    "settlementPeriod 1 is at 00:00 and 48 at 23:30, and each value is published "
    "at startTime + 30 min, so a value covers [startTime, startTime + 30 min). "
    "WINDFOR: the brief describes its startTime as similar to the actuals "
    "startTime, so an hourly value covers [startTime, startTime + 1 h). No "
    "timestamp is shifted."
)

LIMITATIONS = [
    (
        "The cutoff is a provisional market benchmark, not a confirmed company "
        "decision time. The challenge does not name an exchange or give the "
        "client's internal decision schedule. 09:20 Europe/London on D-1 is "
        "used as a conservative hourly day-ahead gate benchmark; confirm the "
        "client's exchange and internal deadline before operational use."
    ),
    (
        "The two datasets may not cover the same generation population. Mean "
        "forecast generation is materially higher than mean actual generation "
        "across the month, which is consistent with WINDFOR covering more wind "
        "capacity than the FUELHH WIND outturn. Metrics are reported raw, without "
        "any adjustment, and this gap is not corrected."
    ),
    (
        "Period labelling is documented and evidence-based for FUELHH, but only "
        "stated indirectly for WINDFOR. Shifting the forecast by one hour changes "
        "the results, so the convention is disclosed rather than treated as "
        "certain."
    ),
    (
        "No financial or procurement conclusion is drawn. The challenge supplies "
        "no cost, price or volume data, so no savings, profitability or trading "
        "impact is claimed."
    ),
    (
        "MAPE is not reported. January contains low-generation periods where a "
        "percentage error relative to actual generation is unstable."
    ),
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyse January 2026 wind forecast accuracy.",
    )
    parser.add_argument("--target-start", default=DEFAULT_TARGET_START)
    parser.add_argument("--target-end", default=DEFAULT_TARGET_END)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=BACKEND_ROOT / "data",
        help="directory holding the Step 3 processed data (default: backend/data)",
    )
    return parser


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/fetch_january_data.py first."
        )
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{path} does not contain a 'records' list")
    return records


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        target_start = parse_utc(args.target_start)
        target_end = parse_utc(args.target_end)
    except ValueError as exc:
        print(f"ERROR invalid date argument: {exc}", file=sys.stderr)
        return 2

    if target_end <= target_start:
        print("ERROR --target-end must be later than --target-start", file=sys.stderr)
        return 2

    processed = args.data_dir / "processed"
    actuals_path = processed / "actuals_january_2026.json"
    forecasts_path = processed / "forecasts_january_2026.json"

    try:
        actual_records = _load_records(actuals_path)
        forecast_records = _load_records(forecasts_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    # 1. Hourly actuals ---------------------------------------------------
    hourly_actuals, actual_summary = build_hourly_actuals(
        actual_records, target_start, target_end
    )
    previous_day_actuals, _ = build_hourly_actuals(
        actual_records, target_start - 24 * ONE_HOUR, target_start
    )

    # 2. Forecast selection ----------------------------------------------
    versions_by_target: dict[datetime, list[ForecastVersion]] = {}
    for record in forecast_records:
        target = parse_utc(record["startTime"])
        if not (target_start <= target < target_end):
            continue
        versions_by_target.setdefault(target, []).append(
            ForecastVersion(
                target=target,
                publish=parse_utc(record["publishTime"]),
                generation=float(record["generation"]),
            )
        )

    selections = [
        select_forecast(target, versions_by_target.get(target, []))
        for target in hour_starts(target_start, target_end)
    ]

    # 3. Alignment and metrics -------------------------------------------
    pairs, audit = align(hourly_actuals, selections)
    metrics = compute_metrics(pairs)
    headline_metrics = compute_headline_metrics(pairs)
    additional_metrics = compute_extended_metrics(
        pairs, [*previous_day_actuals, *hourly_actuals]
    )
    lead_summary = summarise_lead_times(selections)

    selected_count = sum(1 for s in selections if s.is_usable)
    missing_count = sum(1 for s in selections if s.status == "missing_forecast")
    conflict_count = sum(1 for s in selections if s.status == "conflict")
    collapsed = sum(s.collapsed_duplicates for s in selections)

    # 4. Outputs ----------------------------------------------------------
    _write_json(
        processed / "hourly_actuals_january_2026.json",
        {
            "dataset": "derived-hourly-actuals",
            "description": (
                "FUELHH WIND actuals averaged into hourly values. Each hour "
                "requires both 30-minute observations; partial hours are not "
                "averaged. Derived from actuals_january_2026.json."
            ),
            "source_file": actuals_path.name,
            "derived": True,
            "period_labelling": PERIOD_LABELLING,
            "record_count": len(hourly_actuals),
            "records": [
                {
                    "targetStart": to_iso_z(row.target),
                    "targetEnd": to_iso_z(row.target + ONE_HOUR),
                    "generation": round(row.generation, 3),
                    "sourceHalfHourStarts": [to_iso_z(s) for s in row.source_starts],
                }
                for row in hourly_actuals
            ],
        },
    )

    _write_json(
        processed / "selected_forecasts_january_2026.json",
        {
            "dataset": "selected-forecasts",
            "description": (
                "One forecast per delivery target, chosen by the cutoff rule. "
                "Every record carries its publishTime so availability can be "
                "audited. Targets with no eligible forecast are included with "
                "status 'missing_forecast' and no value."
            ),
            "source_file": forecasts_path.name,
            "derived": True,
            "cutoff_rule": CUTOFF_RULE,
            "cutoff_status": "provisional assumption, not prescribed by the challenge",
            "record_count": len(selections),
            "records": [
                {
                    "targetStart": to_iso_z(s.target),
                    "status": s.status,
                    "publishTime": to_iso_z(s.version.publish) if s.version else None,
                    "generation": s.version.generation if s.version else None,
                    "cutoff": to_iso_z(s.cutoff),
                    "leadHours": round(s.lead_hours, 3) if s.lead_hours is not None else None,
                    "eligibleVersions": s.eligible_count,
                    "availableVersions": s.available_count,
                }
                for s in selections
            ],
        },
    )

    _write_json(
        processed / "aligned_analysis_january_2026.json",
        {
            "dataset": "aligned-pairs",
            "description": (
                "Hourly actual and selected forecast matched by target interval. "
                "errorMW = forecastMW - actualMW."
            ),
            "derived": True,
            "pair_count": len(pairs),
            "records": [
                {
                    "targetStart": to_iso_z(pair.target),
                    "actualMW": round(pair.actual_mw, 3),
                    "forecastMW": round(pair.forecast_mw, 3),
                    "errorMW": round(pair.error_mw, 3),
                    "forecastPublishTime": to_iso_z(pair.publish),
                    "leadHours": round(pair.lead_hours, 3),
                }
                for pair in pairs
            ],
        },
    )

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_window": {
            "start": to_iso_z(target_start),
            "end": to_iso_z(target_end),
            "interval": "half-open [start, end)",
            "timezone": "UTC",
            "expected_hours": len(hour_starts(target_start, target_end)),
        },
        "cutoff_assumption": {
            "rule": CUTOFF_RULE,
            "status": "provisional assumption",
            "not_prescribed_by_challenge": True,
            "rationale": (
                "The challenge says purchasing happens one day before delivery "
                "but names no exchange or clock time. 09:20 Europe/London on "
                "D-1 is used as a conservative benchmark for the GB hourly "
                "day-ahead auction; the client-specific decision time remains "
                "unconfirmed. Forecasts published at the cutoff are excluded."
            ),
        },
        "period_labelling": PERIOD_LABELLING,
        "sources": {
            "actuals": {
                "file": actuals_path.name,
                "records": len(actual_records),
                "resolution_seconds": 1800,
            },
            "forecasts": {
                "file": forecasts_path.name,
                "versions": sum(len(v) for v in versions_by_target.values()),
                "targets": len(versions_by_target),
                "resolution_seconds": 3600,
            },
        },
        "counts": {
            "actual_source_records": len(actual_records),
            "valid_hourly_actuals": actual_summary["valid_hours"],
            "unavailable_hourly_actuals": actual_summary["unavailable_hours"],
            "forecast_versions_for_january_targets": sum(
                len(v) for v in versions_by_target.values()
            ),
            "forecast_targets": len(versions_by_target),
            "selected_forecasts": selected_count,
            "missing_forecasts": missing_count,
            "conflicting_latest_publications": conflict_count,
            "collapsed_duplicate_publications": collapsed,
            "missing_actuals_for_selected_forecasts": len(audit["missing_actual"]),
            "unmatched_targets": audit["unmatched_targets"],
            "valid_aligned_pairs": metrics["pair_count"],
        },
        "metrics": metrics,
        "headline_metrics": headline_metrics,
        "additional_metrics": additional_metrics,
        "metric_definitions": {
            "error": "forecastMW - actualMW, in MW. Positive means the forecast was higher.",
            "mae_mw": "Mean of |error| across valid aligned pairs, in MW.",
            "rmse_mw": "Square root of the mean of error^2, in MW.",
            "bias_mw": "Mean of error, in MW. Positive means forecasts ran high.",
            "nmae_percent": "MAE divided by mean actual MW, times 100. Unavailable if mean actual is not strictly positive.",
            "mape": "Not used. Percentage error against low actual generation is unstable.",
        },
        "lead_time_hours": lead_summary,
        "audit": {
            "missing_forecast": audit["missing_forecast"],
            "missing_actual": audit["missing_actual"],
            "conflicting_latest_publications": audit["conflicting_latest_publications"],
            "unavailable_hourly_actuals": actual_summary["unavailable"],
        },
        "limitations": LIMITATIONS,
    }
    _write_json(processed / "analysis_report_january_2026.json", report)

    # 5. Console summary --------------------------------------------------
    print()
    print(f"Analysis window      : {to_iso_z(target_start)} .. {to_iso_z(target_end)}")
    print(f"Cutoff rule          : {CUTOFF_RULE}")
    print()
    print(f"Actual source records        : {len(actual_records)}")
    print(f"Valid hourly actuals         : {actual_summary['valid_hours']}")
    print(f"Unavailable hourly actuals   : {actual_summary['unavailable_hours']}")
    print(f"Forecast versions (Jan)      : {sum(len(v) for v in versions_by_target.values())}")
    print(f"Forecast targets             : {len(versions_by_target)}")
    print(f"Selected forecasts           : {selected_count}")
    print(f"Missing forecasts            : {missing_count}")
    print(f"Conflicting latest publishes : {conflict_count}")
    print(f"Valid aligned pairs          : {metrics['pair_count']}")
    print()
    if metrics["pair_count"]:
        print(f"MAE   : {metrics['mae_mw']:,.1f} MW")
        print(f"RMSE  : {metrics['rmse_mw']:,.1f} MW")
        print(f"Bias  : {metrics['bias_mw']:,.1f} MW  (positive = forecast above actual)")
        print(f"nMAE  : {metrics['nmae_percent']:.2f} % of mean actual")
        print(f"Mean actual   : {metrics['mean_actual_mw']:,.1f} MW")
        print(f"Mean forecast : {metrics['mean_forecast_mw']:,.1f} MW")
    else:
        print("Metrics unavailable: no valid aligned pairs.")
    print()
    if lead_summary.get("count"):
        print(
            "Lead time (hours)    : "
            f"min {lead_summary['min_hours']}, median {lead_summary['median_hours']}, "
            f"max {lead_summary['max_hours']}"
        )
    print(f"Outputs written to   : {processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
