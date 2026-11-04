"""Select the forecast that was genuinely available at a decision cutoff.

The cutoff rule is an **assumption**, not a company requirement. The challenge
brief only says purchases are made "one day before the delivery day"; it does
not state a time of day. The provisional rule used here is:

    for delivery day D, the cutoff is 09:20 Europe/London on D-1, and only
    forecasts with ``publishTime`` strictly earlier than that cutoff are
    eligible.

09:20 is a conservative benchmark for the GB hourly day-ahead auction: it is
earlier than the 09:50 GMT N2EX gate closure. The challenge does not name an
exchange or prescribe the client's internal decision time, so this remains an
explicit benchmark assumption.

Conflict policy
---------------
If two or more eligible records share the latest ``publishTime`` for the same
target:

* identical generation values are treated as duplicates and collapsed to one
  record (counted, not hidden);
* differing generation values are reported as a conflict and the target is
  **excluded** from the metrics. Picking one of two different values published
  at the same instant would be arbitrary, so no value is chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

STATUS_SELECTED = "selected"
STATUS_MISSING = "missing_forecast"
STATUS_CONFLICT = "conflict"
LONDON = ZoneInfo("Europe/London")


@dataclass(frozen=True)
class ForecastVersion:
    """One published forecast for one delivery target."""

    target: datetime
    publish: datetime
    generation: float


@dataclass(frozen=True)
class Selection:
    """Outcome of applying the cutoff rule to one delivery target."""

    target: datetime
    status: str
    version: ForecastVersion | None
    cutoff: datetime
    eligible_count: int
    available_count: int
    lead_hours: float | None = None
    collapsed_duplicates: int = 0
    conflicting: tuple[ForecastVersion, ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        return self.status == STATUS_SELECTED and self.version is not None


def delivery_day_cutoff(target: datetime) -> datetime:
    """Return 09:20 Europe/London on the calendar day before delivery."""
    if target.tzinfo is None:
        raise ValueError("target must be timezone-aware")
    delivery_date = target.astimezone(LONDON).date()
    cutoff_date = delivery_date - timedelta(days=1)
    cutoff_local = datetime.combine(cutoff_date, time(9, 20), tzinfo=LONDON)
    return cutoff_local.astimezone(timezone.utc)


def select_forecast(
    target: datetime,
    versions: Sequence[ForecastVersion],
    *,
    cutoff: datetime | None = None,
) -> Selection:
    """Pick the latest forecast published strictly before ``cutoff``.

    Never falls back to a later publication: if nothing was available in time,
    the target is reported as missing.
    """
    if target.tzinfo is None:
        raise ValueError("target must be timezone-aware")

    effective_cutoff = cutoff if cutoff is not None else delivery_day_cutoff(target)
    if effective_cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")

    for version in versions:
        if version.target != target:
            raise ValueError("all versions must belong to the given target")

    eligible = [v for v in versions if v.publish < effective_cutoff]

    if not eligible:
        return Selection(
            target=target,
            status=STATUS_MISSING,
            version=None,
            cutoff=effective_cutoff,
            eligible_count=0,
            available_count=len(versions),
        )

    latest_publish = max(v.publish for v in eligible)
    latest = [v for v in eligible if v.publish == latest_publish]

    if len(latest) > 1:
        values = {v.generation for v in latest}
        if len(values) > 1:
            return Selection(
                target=target,
                status=STATUS_CONFLICT,
                version=None,
                cutoff=effective_cutoff,
                eligible_count=len(eligible),
                available_count=len(versions),
                conflicting=tuple(sorted(latest, key=lambda v: v.generation)),
            )

    chosen = latest[0]
    lead = (target - chosen.publish).total_seconds() / 3600.0

    return Selection(
        target=target,
        status=STATUS_SELECTED,
        version=chosen,
        cutoff=effective_cutoff,
        eligible_count=len(eligible),
        available_count=len(versions),
        lead_hours=lead,
        collapsed_duplicates=len(latest) - 1,
    )


def summarise_lead_times(selections: Iterable[Selection]) -> dict:
    """Describe the distribution of selected forecast lead times, in hours."""
    leads = sorted(
        s.lead_hours for s in selections if s.lead_hours is not None
    )
    if not leads:
        return {"count": 0}

    def percentile(fraction: float) -> float:
        index = (len(leads) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(leads) - 1)
        weight = index - lower
        return leads[lower] * (1 - weight) + leads[upper] * weight

    bucket_ranges = (
        ("<6h", 0, 6),
        ("6-12h", 6, 12),
        ("12-18h", 12, 18),
        ("18-24h", 18, 24),
        ("24-30h", 24, 30),
        ("30-36h", 30, 36),
        ("36-40h", 36, 40),
        (">=40h", 40, float("inf")),
    )
    buckets = {label: 0 for label, _, _ in bucket_ranges}
    for lead in leads:
        for label, lower, upper in bucket_ranges:
            if lower <= lead < upper:
                buckets[label] += 1
                break

    return {
        "count": len(leads),
        "min_hours": round(leads[0], 3),
        "median_hours": round(percentile(0.5), 3),
        "mean_hours": round(sum(leads) / len(leads), 3),
        "max_hours": round(leads[-1], 3),
        "p05_hours": round(percentile(0.05), 3),
        "p95_hours": round(percentile(0.95), 3),
        "buckets": buckets,
    }
