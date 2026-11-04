"""Tests for the forecast cutoff rule.

All versions here are hand-written synthetic examples used only to exercise the
selection logic. They are not API data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.forecast_selection import (
    STATUS_CONFLICT,
    STATUS_MISSING,
    STATUS_SELECTED,
    ForecastVersion,
    delivery_day_cutoff,
    select_forecast,
    summarise_lead_times,
)

UTC = timezone.utc

# The delivery target used throughout: 1 January 2026, 12:00 UTC.
TARGET = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
# Its cutoff is 2025-12-31T09:20Z (09:20 Europe/London on D-1).


def dt(day: int, hour: int = 0, minute: int = 0, month: int = 1, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def version(publish: datetime, generation: float, target: datetime = TARGET) -> ForecastVersion:
    return ForecastVersion(target=target, publish=publish, generation=generation)


# --------------------------------------------------------------------------
# Cutoff boundary
# --------------------------------------------------------------------------


def test_cutoff_is_0920_london_on_previous_delivery_day() -> None:
    assert delivery_day_cutoff(dt(5, 23)) == dt(4, 9, 20)
    assert delivery_day_cutoff(dt(5, 0)) == dt(4, 9, 20)


def test_cutoff_tracks_british_summer_time() -> None:
    # 30 March is in BST; the previous day is after the spring clock change.
    assert delivery_day_cutoff(dt(30, 12, month=3)) == dt(29, 8, 20, month=3)


def test_forecast_published_exactly_at_cutoff_is_excluded() -> None:
    result = select_forecast(TARGET, [version(dt(31, 9, 20, month=12, year=2025), 5000.0)])

    assert result.status == STATUS_MISSING
    assert result.version is None
    assert result.eligible_count == 0


def test_forecast_published_one_second_before_cutoff_is_eligible() -> None:
    publish = dt(31, 9, 19, month=12, year=2025).replace(second=59)

    result = select_forecast(TARGET, [version(publish, 5000.0)])

    assert result.status == STATUS_SELECTED
    assert result.version is not None
    assert result.version.generation == 5000.0


def test_forecast_before_cutoff_is_eligible() -> None:
    result = select_forecast(TARGET, [version(dt(31, 8, month=12, year=2025), 9000.0)])

    assert result.status == STATUS_SELECTED
    assert result.version.generation == 9000.0


# --------------------------------------------------------------------------
# Latest eligible wins
# --------------------------------------------------------------------------


def test_latest_eligible_forecast_wins_and_post_cutoff_version_is_ignored() -> None:
    versions = [
        version(dt(31, 2, month=12, year=2025), 8000.0),          # older, eligible
        version(dt(31, 9, 0, month=12, year=2025), 9500.0),      # newest eligible
        version(dt(1, 1), 12000.0),                               # after cutoff
        version(dt(1, 6), 13000.0),                               # after cutoff
    ]

    result = select_forecast(TARGET, versions)

    assert result.status == STATUS_SELECTED
    assert result.version is not None
    assert result.version.generation == 9500.0
    assert result.version.publish == dt(31, 9, 0, month=12, year=2025)
    assert result.eligible_count == 2
    assert result.available_count == 4


def test_lead_time_is_measured_from_publish_to_target() -> None:
    result = select_forecast(
        TARGET, [version(dt(31, 0, month=12, year=2025), 9000.0)]
    )

    assert result.lead_hours == pytest.approx(36.0)


# --------------------------------------------------------------------------
# Missing and conflicting
# --------------------------------------------------------------------------


def test_no_eligible_forecast_yields_missing_and_no_substitution() -> None:
    versions = [version(dt(1, 3), 11000.0), version(dt(1, 9), 11500.0)]

    result = select_forecast(TARGET, versions)

    assert result.status == STATUS_MISSING
    assert result.version is None
    assert result.available_count == 2
    assert result.eligible_count == 0


def test_identical_duplicates_at_latest_publish_are_collapsed() -> None:
    latest = dt(31, 9, 0, month=12, year=2025)
    versions = [
        version(dt(31, 2, month=12, year=2025), 8000.0),
        version(latest, 9500.0),
        version(latest, 9500.0),
    ]

    result = select_forecast(TARGET, versions)

    assert result.status == STATUS_SELECTED
    assert result.version is not None
    assert result.version.generation == 9500.0
    assert result.collapsed_duplicates == 1


def test_different_values_at_latest_publish_are_reported_as_conflict() -> None:
    latest = dt(31, 9, 0, month=12, year=2025)
    versions = [version(latest, 9500.0), version(latest, 9700.0)]

    result = select_forecast(TARGET, versions)

    assert result.status == STATUS_CONFLICT
    assert result.version is None, "no arbitrary choice may be made"
    assert len(result.conflicting) == 2
    assert {v.generation for v in result.conflicting} == {9500.0, 9700.0}


def test_conflict_at_latest_publish_does_not_fall_back_to_older_version() -> None:
    latest = dt(31, 9, 0, month=12, year=2025)
    versions = [
        version(dt(31, 2, month=12, year=2025), 8000.0),
        version(latest, 9500.0),
        version(latest, 9700.0),
    ]

    result = select_forecast(TARGET, versions)

    assert result.status == STATUS_CONFLICT
    assert result.version is None


def test_versions_for_a_different_target_are_rejected() -> None:
    with pytest.raises(ValueError, match="belong to the given target"):
        select_forecast(TARGET, [version(dt(31, 2, month=12, year=2025), 1.0, target=dt(1, 13))])


# --------------------------------------------------------------------------
# Lead-time summary
# --------------------------------------------------------------------------


def test_lead_time_summary_reports_distribution() -> None:
    selections = [
        select_forecast(TARGET, [version(dt(31, 0, month=12, year=2025), 1.0)]),   # 36 h
        select_forecast(dt(1, 13), [version(dt(31, 9, 0, month=12, year=2025), 2.0, target=dt(1, 13))]),  # 28 h
    ]

    summary = summarise_lead_times(selections)

    assert summary["count"] == 2
    assert summary["min_hours"] == pytest.approx(28.0)
    assert summary["max_hours"] == pytest.approx(36.0)
    assert sum(summary["buckets"].values()) == 2


def test_lead_time_summary_handles_no_selections() -> None:
    assert summarise_lead_times([]) == {"count": 0}
