"""Retrieve, validate and store January 2026 Elexon wind data.

Run from the ``backend/`` directory:

    python scripts/fetch_january_data.py

What it does
------------
1. Retrieves raw FUELHH (WIND) actuals and WINDFOR forecasts from the official
   Elexon API, using publication windows.
2. Saves the raw responses unchanged under ``backend/data/raw/``.
3. Validates and normalises them, keeping only target periods that fall inside
   the January 2026 delivery window.
4. Saves the validated datasets under ``backend/data/processed/`` and a full
   validation report next to them.

Nothing here selects a forecast version or computes accuracy. Every retrieved
forecast publication version is preserved so that Step 4 can apply the agreed
cutoff rule.

Publication windows (justified by the verified API behaviour)
-------------------------------------------------------------
* Actuals: a FUELHH record is published 30 minutes after its target period
  starts. A publication window of 2026-01-01T00:00Z .. 2026-02-01T00:00Z
  therefore covers every January target. It also returns one boundary record
  whose target is 2025-12-31T23:30Z; that row is reported and excluded by the
  target-time filter.
* Forecasts: WINDFOR publishes roughly every three hours and each publication
  looks up to ~66 hours ahead. The earliest publication that already contained
  the 2026-01-01T00:00Z target was 2025-12-30T02:30Z (verified against the live
  API), so the window starts at 2025-12-30T00:00Z for margin. It ends at
  2026-02-01T00:00Z, which includes every publication that could precede a
  January delivery day.

Exit codes
----------
0  success
1  validation produced warnings that need attention (data still saved)
2  the Elexon API could not be used (nothing saved)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.data_validation import (  # noqa: E402
    parse_utc,
    to_iso_z,
    validate_actuals,
    validate_forecasts,
)
from app.services.elexon_client import ElexonClient, ElexonAPIError  # noqa: E402

# Analysis scope agreed with the user: delivery periods 1-31 January 2026 (UTC).
DEFAULT_TARGET_START = "2026-01-01T00:00:00Z"
DEFAULT_TARGET_END = "2026-02-01T00:00:00Z"

# Publication windows, see the module docstring for the reasoning.
DEFAULT_ACTUAL_PUBLISH_START = "2025-12-31T00:00:00Z"
DEFAULT_ACTUAL_PUBLISH_END = "2026-02-01T00:00:00Z"
DEFAULT_FORECAST_PUBLISH_START = "2025-12-30T00:00:00Z"
DEFAULT_FORECAST_PUBLISH_END = "2026-02-01T00:00:00Z"

logger = logging.getLogger("fetch_january_data")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch, validate and store January 2026 Elexon wind data.",
    )
    parser.add_argument(
        "--target-start",
        default=DEFAULT_TARGET_START,
        help="first delivery period start (UTC, inclusive)",
    )
    parser.add_argument(
        "--target-end",
        default=DEFAULT_TARGET_END,
        help="delivery period end (UTC, exclusive)",
    )
    parser.add_argument(
        "--actual-publish-start",
        default=DEFAULT_ACTUAL_PUBLISH_START,
        help="FUELHH publication window start (UTC, inclusive)",
    )
    parser.add_argument(
        "--actual-publish-end",
        default=DEFAULT_ACTUAL_PUBLISH_END,
        help="FUELHH publication window end (UTC, inclusive)",
    )
    parser.add_argument(
        "--forecast-publish-start",
        default=DEFAULT_FORECAST_PUBLISH_START,
        help="WINDFOR publication window start (UTC, inclusive)",
    )
    parser.add_argument(
        "--forecast-publish-end",
        default=DEFAULT_FORECAST_PUBLISH_END,
        help="WINDFOR publication window end (UTC, inclusive)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BACKEND_ROOT / "data",
        help="directory for raw and processed data (default: backend/data)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override the Elexon API base URL (testing only)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=4,
        help="attempts per request, including the first (default: 4)",
    )
    return parser


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        target_start = parse_utc(args.target_start)
        target_end = parse_utc(args.target_end)
        actual_publish_start = parse_utc(args.actual_publish_start)
        actual_publish_end = parse_utc(args.actual_publish_end)
        forecast_publish_start = parse_utc(args.forecast_publish_start)
        forecast_publish_end = parse_utc(args.forecast_publish_end)
    except ValueError as exc:
        logger.error("Invalid date argument: %s", exc)
        return 2

    if target_end <= target_start:
        logger.error("--target-end must be later than --target-start")
        return 2

    # One prior delivery day is retained solely for the naive same-hour
    # previous-day baseline. The scored forecast/actual window remains January.
    actual_target_start = target_start - timedelta(days=1)

    out_dir: Path = args.out_dir
    raw_dir = out_dir / "raw"
    processed_dir = out_dir / "processed"

    logger.info(
        "Target delivery window : %s .. %s",
        to_iso_z(target_start),
        to_iso_z(target_end),
    )

    client_kwargs: dict[str, Any] = {
        "timeout_seconds": args.timeout,
        "max_attempts": args.max_attempts,
    }
    if args.base_url:
        client_kwargs["base_url"] = args.base_url

    try:
        with ElexonClient(**client_kwargs) as client:
            logger.info("Fetching FUELHH actuals (fuelType=WIND) ...")
            raw_actuals = client.fetch_fuelhh_wind(
                actual_publish_start, actual_publish_end
            )

            logger.info("Fetching WINDFOR forecasts (all publication versions) ...")
            raw_forecasts = client.fetch_windfor(
                forecast_publish_start, forecast_publish_end
            )
    except ElexonAPIError as exc:
        logger.error("Elexon API failure: %s", exc)
        logger.error("No data was saved. Nothing has been substituted.")
        return 2
    except Exception as exc:  # noqa: BLE001 - surfaced, never hidden
        logger.error("Unexpected failure while retrieving data: %s", exc)
        logger.error("No data was saved. Nothing has been substituted.")
        return 2

    # Raw responses are stored byte-for-byte as Elexon returned them.
    _write_json(raw_dir / "actuals_january_2026.json", raw_actuals)
    _write_json(raw_dir / "forecasts_january_2026.json", raw_forecasts)
    logger.info("Raw responses saved under %s", raw_dir)

    actuals, actual_report = validate_actuals(
        raw_actuals, target_start=actual_target_start, target_end=target_end
    )
    forecasts, forecast_report = validate_forecasts(
        raw_forecasts, target_start=target_start, target_end=target_end
    )

    _write_json(
        processed_dir / "actuals_january_2026.json",
        {
            "dataset": "FUELHH",
            "description": (
                "Validated and normalised FUELHH WIND actuals for January 2026 "
                "plus the preceding day required by the naive baseline. Derived "
                "from the raw response; not a raw API payload."
            ),
            "source": "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_window": {
                "start": to_iso_z(actual_target_start),
                "end": to_iso_z(target_end),
                "interval": "half-open [start, end)",
            },
            "record_count": len(actuals),
            "records": actuals,
        },
    )
    _write_json(
        processed_dir / "forecasts_january_2026.json",
        {
            "dataset": "WINDFOR",
            "description": (
                "Validated and normalised WINDFOR forecasts filtered to January "
                "2026 target times. Every publication version is retained; no "
                "cutoff selection has been applied. Derived from the raw "
                "response; not a raw API payload."
            ),
            "source": "https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_window": {
                "start": to_iso_z(target_start),
                "end": to_iso_z(target_end),
                "interval": "half-open [start, end)",
            },
            "record_count": len(forecasts),
            "records": forecasts,
        },
    )

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_window": {
            "start": to_iso_z(target_start),
            "end": to_iso_z(target_end),
        },
        "publication_windows": {
            "FUELHH": {
                "from": to_iso_z(actual_publish_start),
                "to": to_iso_z(actual_publish_end),
            },
            "WINDFOR": {
                "from": to_iso_z(forecast_publish_start),
                "to": to_iso_z(forecast_publish_end),
            },
        },
        "reports": {
            "FUELHH": actual_report.as_dict(),
            "WINDFOR": forecast_report.as_dict(),
        },
    }
    _write_json(processed_dir / "validation_report.json", report)

    print()
    for line in actual_report.summary_lines():
        print(line)
    print()
    for line in forecast_report.summary_lines():
        print(line)
    print()
    print(f"Processed datasets written to: {processed_dir}")
    print(f"Validation report written to : {processed_dir / 'validation_report.json'}")

    problems = (
        actual_report.rejected_rows
        + forecast_report.rejected_rows
        + actual_report.conflicting_records
        + forecast_report.conflicting_records
    )
    if problems:
        print()
        print(f"ATTENTION: {problems} rejected/conflicting record(s) - see the report.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
