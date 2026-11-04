"""Validation, normalisation and target-period filtering of Elexon records.

Design rules
------------
* Nothing is dropped silently. Every invalid row, exact duplicate and
  conflicting record is counted and listed in a :class:`DatasetReport`.
* Timestamps must carry a timezone. Elexon documents UTC timestamps, so a
  timestamp without an offset is **rejected** rather than guessed at.
* ``generation`` must be a finite number. Booleans, non-numeric strings,
  ``NaN`` and infinities are rejected.
* Deduplication rules (documented here and in the README):

  - **Actuals (FUELHH)** are identified by ``startTime``. If several rows share
    a ``startTime``, identical copies are counted as exact duplicates and one is
    kept; if the content differs, the row with the latest ``publishTime`` is
    kept and the rest are reported as conflicts.
  - **Forecasts (WINDFOR)** are identified by ``(startTime, publishTime)``.
    Multiple publication versions for the same ``startTime`` are legitimate and
    all preserved; only identical ``(startTime, publishTime)`` copies are
    deduplicated.

* Target-period filtering is half-open: ``start <= startTime < end``.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

ACTUAL_DATASET = "FUELHH"
FORECAST_DATASET = "WINDFOR"
WIND_FUEL_TYPE = "WIND"

#: Resolution the official documentation states for each dataset. Used only to
#: compare against what the data actually contains - never assumed.
DOCUMENTED_RESOLUTION_SECONDS = {
    ACTUAL_DATASET: 30 * 60,
    FORECAST_DATASET: 60 * 60,
}

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Primitive parsing helpers
# --------------------------------------------------------------------------


def parse_utc(value: Any) -> datetime:
    """Parse an Elexon timestamp and return an aware UTC datetime.

    Raises ``ValueError`` for anything that is not an ISO-8601 string with an
    explicit offset. A missing offset is rejected instead of being assumed UTC.
    """
    if not isinstance(value, str):
        raise ValueError(f"timestamp must be a string, got {type(value).__name__}")

    text = value.strip()
    if not text:
        raise ValueError("timestamp is empty")

    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp {value!r}") from exc

    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {value!r} has no timezone offset")

    return parsed.astimezone(timezone.utc)


def to_iso_z(value: datetime | None) -> str | None:
    """Render a datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("cannot format a timezone-naive datetime")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def coerce_generation(value: Any) -> float:
    """Return ``generation`` as a finite float, or raise ``ValueError``."""
    if isinstance(value, bool):
        raise ValueError("generation must be a number, got a boolean")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"generation {value!r} is not numeric") from exc
    else:
        raise ValueError(
            f"generation must be a number, got {type(value).__name__}"
        )

    if not math.isfinite(number):
        raise ValueError(f"generation {value!r} is not finite")
    return number


# --------------------------------------------------------------------------
# Report types
# --------------------------------------------------------------------------


class RowError(ValueError):
    """A single record failed validation."""

    def __init__(self, reason: str, kind: str = "invalid") -> None:
        super().__init__(reason)
        self.kind = kind  # "missing" | "invalid" | "non_finite"


@dataclass(frozen=True)
class RejectedRow:
    index: int
    reason: str
    record: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "reason": self.reason, "record": dict(self.record)}


@dataclass
class DatasetReport:
    """Everything that happened to a raw response, in one auditable object."""

    dataset: str
    source_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    missing_field_rows: int = 0
    invalid_value_rows: int = 0
    non_finite_rows: int = 0
    exact_duplicates: int = 0
    conflicting_records: int = 0
    distinct_targets: int = 0
    min_start_time: datetime | None = None
    max_start_time: datetime | None = None
    min_publish_time: datetime | None = None
    max_publish_time: datetime | None = None
    resolution_seconds: int | None = None
    resolution_counts: dict[int, int] = field(default_factory=dict)
    irregular_gap_count: int = 0
    versions_per_target_min: int | None = None
    versions_per_target_max: int | None = None
    target_rows_outside_window: int = 0
    outside_window_min_start: datetime | None = None
    outside_window_max_start: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    duplicates: list[RejectedRow] = field(default_factory=list)
    conflicts: list[RejectedRow] = field(default_factory=list)

    # -- derived helpers --------------------------------------------------

    def check_documented_resolution(self) -> None:
        """Compare observed resolution with the documented one, without assuming."""
        expected = DOCUMENTED_RESOLUTION_SECONDS.get(self.dataset)
        if expected is None or self.resolution_seconds is None:
            return
        if self.resolution_seconds != expected:
            self.warnings.append(
                f"Observed resolution is {self.resolution_seconds}s but the "
                f"documentation states {expected}s for {self.dataset}."
            )
        if self.irregular_gap_count:
            self.warnings.append(
                f"{self.irregular_gap_count} gap(s) differ from the dominant "
                f"{self.resolution_seconds}s spacing - possible missing periods."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "source_rows": self.source_rows,
            "valid_rows": self.valid_rows,
            "rejected_rows": self.rejected_rows,
            "missing_field_rows": self.missing_field_rows,
            "invalid_value_rows": self.invalid_value_rows,
            "non_finite_rows": self.non_finite_rows,
            "exact_duplicates": self.exact_duplicates,
            "conflicting_records": self.conflicting_records,
            "distinct_targets": self.distinct_targets,
            "min_start_time": to_iso_z(self.min_start_time),
            "max_start_time": to_iso_z(self.max_start_time),
            "min_publish_time": to_iso_z(self.min_publish_time),
            "max_publish_time": to_iso_z(self.max_publish_time),
            "resolution_seconds": self.resolution_seconds,
            "resolution_counts": {
                str(seconds): count
                for seconds, count in sorted(self.resolution_counts.items())
            },
            "irregular_gap_count": self.irregular_gap_count,
            "versions_per_target_min": self.versions_per_target_min,
            "versions_per_target_max": self.versions_per_target_max,
            "target_rows_outside_window": self.target_rows_outside_window,
            "outside_window_min_start": to_iso_z(self.outside_window_min_start),
            "outside_window_max_start": to_iso_z(self.outside_window_max_start),
            "warnings": list(self.warnings),
            "rejected": [row.as_dict() for row in self.rejected],
            "duplicates": [row.as_dict() for row in self.duplicates],
            "conflicts": [row.as_dict() for row in self.conflicts],
        }

    def summary_lines(self) -> list[str]:
        """Human-readable summary for console output."""
        lines = [
            f"[{self.dataset}] source rows            : {self.source_rows}",
            f"[{self.dataset}] valid rows (kept)      : {self.valid_rows}",
            f"[{self.dataset}] rejected rows          : {self.rejected_rows}"
            f" (missing field {self.missing_field_rows},"
            f" invalid value {self.invalid_value_rows},"
            f" non-finite {self.non_finite_rows})",
            f"[{self.dataset}] exact duplicates       : {self.exact_duplicates}",
            f"[{self.dataset}] conflicting records    : {self.conflicting_records}",
            f"[{self.dataset}] distinct target times  : {self.distinct_targets}",
            f"[{self.dataset}] target time range      : "
            f"{to_iso_z(self.min_start_time)} .. {to_iso_z(self.max_start_time)}",
            f"[{self.dataset}] publish time range     : "
            f"{to_iso_z(self.min_publish_time)} .. {to_iso_z(self.max_publish_time)}",
            f"[{self.dataset}] observed resolution    : "
            f"{self.resolution_seconds}s"
            + (
                f" (documented {DOCUMENTED_RESOLUTION_SECONDS[self.dataset]}s)"
                if self.dataset in DOCUMENTED_RESOLUTION_SECONDS
                else ""
            ),
        ]
        if self.versions_per_target_min is not None:
            lines.append(
                f"[{self.dataset}] forecast versions per target: "
                f"{self.versions_per_target_min}..{self.versions_per_target_max}"
            )
        if self.target_rows_outside_window:
            lines.append(
                f"[{self.dataset}] rows outside target window: "
                f"{self.target_rows_outside_window} "
                f"({to_iso_z(self.outside_window_min_start)} .. "
                f"{to_iso_z(self.outside_window_max_start)})"
            )
        for warning in self.warnings:
            lines.append(f"[{self.dataset}] WARNING: {warning}")
        return lines


@dataclass
class _Row:
    """Internal representation with parsed datetimes."""

    index: int
    start: datetime
    publish: datetime | None
    generation: float
    record: dict[str, Any]
    raw: Mapping[str, Any]


# --------------------------------------------------------------------------
# Record normalisation
# --------------------------------------------------------------------------


def _require(record: Mapping[str, Any], key: str) -> Any:
    if key not in record:
        raise RowError(f"missing required field {key!r}", kind="missing")
    value = record[key]
    if value is None:
        raise RowError(f"required field {key!r} is null", kind="missing")
    return value


def _parse_start(record: Mapping[str, Any]) -> datetime:
    try:
        return parse_utc(_require(record, "startTime"))
    except RowError:
        raise
    except ValueError as exc:
        raise RowError(f"invalid startTime: {exc}") from exc


def _parse_publish(record: Mapping[str, Any], *, required: bool) -> datetime | None:
    if required:
        raw = _require(record, "publishTime")
    else:
        raw = record.get("publishTime")
        if raw is None:
            return None
    try:
        return parse_utc(raw)
    except RowError:
        raise
    except ValueError as exc:
        raise RowError(f"invalid publishTime: {exc}") from exc


def _parse_generation(record: Mapping[str, Any]) -> float:
    try:
        return coerce_generation(_require(record, "generation"))
    except RowError:
        raise
    except ValueError as exc:
        kind = "non_finite" if "finite" in str(exc) else "invalid"
        raise RowError(f"invalid generation: {exc}", kind=kind) from exc


def _normalise_actual(record: Mapping[str, Any], index: int) -> _Row:
    if not isinstance(record, Mapping):
        raise RowError(f"record must be an object, got {type(record).__name__}")

    dataset = record.get("dataset")
    if dataset is not None and str(dataset).upper() != ACTUAL_DATASET:
        raise RowError(f"unexpected dataset {dataset!r}, expected {ACTUAL_DATASET!r}")

    fuel_type = record.get("fuelType")
    if fuel_type is None:
        raise RowError("missing required field 'fuelType'", kind="missing")
    if str(fuel_type).upper() != WIND_FUEL_TYPE:
        raise RowError(f"unexpected fuelType {fuel_type!r}, expected WIND")

    start = _parse_start(record)
    publish = _parse_publish(record, required=False)
    generation = _parse_generation(record)

    settlement_period = record.get("settlementPeriod")
    if settlement_period is not None and not isinstance(settlement_period, int):
        raise RowError("settlementPeriod must be an integer")

    normalised = {
        "startTime": to_iso_z(start),
        "publishTime": to_iso_z(publish),
        "generation": generation,
        "fuelType": WIND_FUEL_TYPE,
        "settlementDate": record.get("settlementDate"),
        "settlementPeriod": settlement_period,
    }
    return _Row(index, start, publish, generation, normalised, record)


def _normalise_forecast(record: Mapping[str, Any], index: int) -> _Row:
    if not isinstance(record, Mapping):
        raise RowError(f"record must be an object, got {type(record).__name__}")

    dataset = record.get("dataset")
    if dataset is not None and str(dataset).upper() != FORECAST_DATASET:
        raise RowError(f"unexpected dataset {dataset!r}, expected {FORECAST_DATASET!r}")

    start = _parse_start(record)
    publish = _parse_publish(record, required=True)
    generation = _parse_generation(record)

    normalised = {
        "startTime": to_iso_z(start),
        "publishTime": to_iso_z(publish),
        "generation": generation,
    }
    return _Row(index, start, publish, generation, normalised, record)


# --------------------------------------------------------------------------
# Shared statistics
# --------------------------------------------------------------------------


def _apply_statistics(rows: list[_Row], report: DatasetReport) -> None:
    if not rows:
        return

    report.valid_rows = len(rows)
    starts = sorted({row.start for row in rows})
    report.distinct_targets = len(starts)
    report.min_start_time = starts[0]
    report.max_start_time = starts[-1]

    publishes = [row.publish for row in rows if row.publish is not None]
    if publishes:
        report.min_publish_time = min(publishes)
        report.max_publish_time = max(publishes)

    gaps = [
        int((later - earlier).total_seconds())
        for earlier, later in zip(starts, starts[1:])
    ]
    if gaps:
        counts = Counter(gaps)
        report.resolution_counts = dict(counts)
        dominant, _ = counts.most_common(1)[0]
        report.resolution_seconds = dominant
        report.irregular_gap_count = sum(
            count for gap, count in counts.items() if gap != dominant
        )


def _report_row_error(report: DatasetReport, error: RowError, index: int, raw: Any) -> None:
    report.rejected_rows += 1
    if error.kind == "missing":
        report.missing_field_rows += 1
    elif error.kind == "non_finite":
        report.non_finite_rows += 1
    else:
        report.invalid_value_rows += 1
    record = raw if isinstance(raw, Mapping) else {"value": raw}
    report.rejected.append(RejectedRow(index, str(error), record))


def _resolve_duplicates(
    rows: Iterable[_Row],
    *,
    identity,
    report: DatasetReport,
    keep_latest_publish: bool,
) -> list[_Row]:
    grouped: dict[Any, list[_Row]] = {}
    for row in rows:
        grouped.setdefault(identity(row), []).append(row)

    kept: list[_Row] = []
    for group in grouped.values():
        if len(group) == 1:
            kept.append(group[0])
            continue

        signatures = {(row.publish, row.generation) for row in group}
        if len(signatures) == 1:
            report.exact_duplicates += len(group) - 1
            kept.append(group[0])
            for row in group[1:]:
                report.duplicates.append(
                    RejectedRow(row.index, "exact duplicate; one copy kept", row.raw)
                )
            continue

        report.conflicting_records += 1
        if keep_latest_publish:
            chosen = max(group, key=lambda r: r.publish or _EPOCH)
            reason = (
                "conflicting values for the same startTime; "
                "kept the latest publishTime"
            )
        else:
            chosen = group[0]
            reason = (
                "conflicting values for the same startTime and publishTime; "
                "kept the first occurrence"
            )
        kept.append(chosen)
        for row in group:
            if row is not chosen:
                report.conflicts.append(RejectedRow(row.index, reason, row.raw))

    return kept


def _sort_rows(rows: list[_Row]) -> list[_Row]:
    return sorted(rows, key=lambda r: (r.start, r.publish or _EPOCH))


# --------------------------------------------------------------------------
# Public validation entry points
# --------------------------------------------------------------------------


def validate_actuals(
    records: Iterable[Mapping[str, Any]],
    *,
    target_start: datetime | None = None,
    target_end: datetime | None = None,
) -> tuple[list[dict[str, Any]], DatasetReport]:
    """Validate FUELHH records and return normalised rows plus a report."""
    report = DatasetReport(dataset=ACTUAL_DATASET)
    raw_records = list(records)
    report.source_rows = len(raw_records)

    rows: list[_Row] = []
    for index, raw in enumerate(raw_records):
        try:
            rows.append(_normalise_actual(raw, index))
        except RowError as exc:
            _report_row_error(report, exc, index, raw)

    rows = _resolve_duplicates(
        rows,
        identity=lambda r: r.start,
        report=report,
        keep_latest_publish=True,
    )
    rows = _sort_rows(rows)

    if target_start is not None and target_end is not None:
        rows, outside = filter_rows_by_target(rows, target_start, target_end)
        _record_window_filter(report, outside)

    _apply_statistics(rows, report)
    report.check_documented_resolution()
    return [row.record for row in rows], report


def validate_forecasts(
    records: Iterable[Mapping[str, Any]],
    *,
    target_start: datetime | None = None,
    target_end: datetime | None = None,
) -> tuple[list[dict[str, Any]], DatasetReport]:
    """Validate WINDFOR records and return normalised rows plus a report.

    Every publication version of every target time is preserved.
    """
    report = DatasetReport(dataset=FORECAST_DATASET)
    raw_records = list(records)
    report.source_rows = len(raw_records)

    rows: list[_Row] = []
    for index, raw in enumerate(raw_records):
        try:
            rows.append(_normalise_forecast(raw, index))
        except RowError as exc:
            _report_row_error(report, exc, index, raw)

    rows = _resolve_duplicates(
        rows,
        identity=lambda r: (r.start, r.publish),
        report=report,
        keep_latest_publish=False,
    )
    rows = _sort_rows(rows)

    if target_start is not None and target_end is not None:
        rows, outside = filter_rows_by_target(rows, target_start, target_end)
        _record_window_filter(report, outside)

    _apply_statistics(rows, report)

    if rows:
        versions = Counter(row.start for row in rows)
        report.versions_per_target_min = min(versions.values())
        report.versions_per_target_max = max(versions.values())

    report.check_documented_resolution()
    return [row.record for row in rows], report


def filter_rows_by_target(
    rows: list[_Row], target_start: datetime, target_end: datetime
) -> tuple[list[_Row], list[_Row]]:
    """Split rows into inside/outside ``[target_start, target_end)``."""
    if target_start.tzinfo is None or target_end.tzinfo is None:
        raise ValueError("target window bounds must be timezone-aware")
    if target_end <= target_start:
        raise ValueError("target_end must be later than target_start")

    inside = [row for row in rows if target_start <= row.start < target_end]
    outside = [row for row in rows if not (target_start <= row.start < target_end)]
    return inside, outside


def _record_window_filter(report: DatasetReport, outside: list[_Row]) -> None:
    report.target_rows_outside_window = len(outside)
    if outside:
        report.outside_window_min_start = min(row.start for row in outside)
        report.outside_window_max_start = max(row.start for row in outside)


def filter_target_window(
    records: Iterable[Mapping[str, Any]],
    target_start: datetime,
    target_end: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter already-normalised records by target ``startTime``.

    Uses a half-open interval: ``target_start <= startTime < target_end``.
    Returns ``(kept, dropped)`` so callers can report what was excluded.
    """
    if target_end <= target_start:
        raise ValueError("target_end must be later than target_start")

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for record in records:
        start = parse_utc(record["startTime"])
        (kept if target_start <= start < target_end else dropped).append(dict(record))
    return kept, dropped
