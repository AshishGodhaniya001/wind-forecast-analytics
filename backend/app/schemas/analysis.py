"""Pydantic response models for the analysis endpoints.

The models mirror the generated JSON artefacts field-for-field. That is
deliberate: the API is a typed view over files produced by
``scripts/analyse_january_data.py``, not a second implementation of the
analysis. Mirroring the names makes the two easy to compare during review.

Validation is strict (``extra="forbid"``, no NaN/infinity). If an artefact
drifts from this contract the API fails loudly instead of returning a
half-understood payload.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.services.data_validation import parse_utc


def _check_utc_timestamp(value: str) -> str:
    """Reject anything that is not an ISO-8601 timestamp with an offset."""
    parse_utc(value)  # raises ValueError, which Pydantic turns into an error
    return value


UtcTimestamp = Annotated[str, AfterValidator(_check_utc_timestamp)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# --------------------------------------------------------------------------
# Report sections
# --------------------------------------------------------------------------


class AnalysisWindow(_StrictModel):
    start: UtcTimestamp
    end: UtcTimestamp
    interval: str
    timezone: Literal["UTC"]
    expected_hours: int = Field(ge=0)


class CutoffAssumption(_StrictModel):
    rule: str
    status: str
    not_prescribed_by_challenge: bool
    rationale: str


class ActualSource(_StrictModel):
    file: str
    records: int = Field(ge=0)
    resolution_seconds: int = Field(gt=0)


class ForecastSource(_StrictModel):
    file: str
    versions: int = Field(ge=0)
    targets: int = Field(ge=0)
    resolution_seconds: int = Field(gt=0)


class Sources(_StrictModel):
    actuals: ActualSource
    forecasts: ForecastSource


class Counts(_StrictModel):
    actual_source_records: int = Field(ge=0)
    valid_hourly_actuals: int = Field(ge=0)
    unavailable_hourly_actuals: int = Field(ge=0)
    forecast_versions_for_january_targets: int = Field(ge=0)
    forecast_targets: int = Field(ge=0)
    selected_forecasts: int = Field(ge=0)
    missing_forecasts: int = Field(ge=0)
    conflicting_latest_publications: int = Field(ge=0)
    collapsed_duplicate_publications: int = Field(ge=0)
    missing_actuals_for_selected_forecasts: int = Field(ge=0)
    unmatched_targets: int = Field(ge=0)
    valid_aligned_pairs: int = Field(ge=0)


class Metrics(_StrictModel):
    pair_count: int = Field(ge=0)
    mae_mw: float | None = None
    rmse_mw: float | None = None
    bias_mw: float | None = None
    nmae_percent: float | None = None
    mean_actual_mw: float | None = None
    mean_forecast_mw: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _values_match_pair_count(self) -> "Metrics":
        """Zero pairs must be reported as unavailable, never as zeros."""
        required = (
            self.mae_mw,
            self.rmse_mw,
            self.bias_mw,
            self.mean_actual_mw,
            self.mean_forecast_mw,
        )
        if self.pair_count == 0:
            if any(value is not None for value in required) or self.nmae_percent is not None:
                raise ValueError("metrics must be null when pair_count is 0")
        elif any(value is None for value in required):
            raise ValueError("metrics must be present when pair_count is greater than 0")
        return self


class HeadlineMetrics(_StrictModel):
    overforecast_share_percent: float | None = Field(default=None, ge=0, le=100)
    rmse_after_bias_mw: float | None = Field(default=None, ge=0)
    bias_squared_error_share_percent: float | None = Field(default=None, ge=0, le=100)
    bias_percent_of_mean_actual: float | None = None
    headline_text: str


class ErrorGroup(_StrictModel):
    pair_count: int = Field(ge=0)
    mae_mw: float | None = Field(default=None, ge=0)
    bias_mw: float | None = None

    @model_validator(mode="after")
    def _empty_values_are_null(self) -> "ErrorGroup":
        if self.pair_count == 0 and (self.mae_mw is not None or self.bias_mw is not None):
            raise ValueError("empty error groups must have null metrics")
        if self.pair_count > 0 and (self.mae_mw is None or self.bias_mw is None):
            raise ValueError("non-empty error groups must have metrics")
        return self


class LeadTimeErrorGroup(ErrorGroup):
    bucket: str


class HourOfDayErrorGroup(ErrorGroup):
    hour_utc: int = Field(ge=0, le=23)


class HourOfDayMaeExtremes(_StrictModel):
    highest_hour_utc: int | None = Field(default=None, ge=0, le=23)
    highest_mae_mw: float | None = Field(default=None, ge=0)
    lowest_hour_utc: int | None = Field(default=None, ge=0, le=23)
    lowest_mae_mw: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _hour_and_mae_are_paired(self) -> "HourOfDayMaeExtremes":
        if (self.highest_hour_utc is None) != (self.highest_mae_mw is None):
            raise ValueError("highest hour and MAE must be present together")
        if (self.lowest_hour_utc is None) != (self.lowest_mae_mw is None):
            raise ValueError("lowest hour and MAE must be present together")
        return self


class NaiveBaseline(_StrictModel):
    pair_count: int = Field(ge=0)
    mae_mw: float | None = Field(default=None, ge=0)
    rmse_mw: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _empty_values_are_null(self) -> "NaiveBaseline":
        if self.pair_count == 0 and (self.mae_mw is not None or self.rmse_mw is not None):
            raise ValueError("empty baseline must have null metrics")
        if self.pair_count > 0 and (self.mae_mw is None or self.rmse_mw is None):
            raise ValueError("non-empty baseline must have metrics")
        return self


class LargestMiss(_StrictModel):
    target_start: UtcTimestamp
    date_utc: str
    hour_utc: int = Field(ge=0, le=23)
    absolute_error_mw: float = Field(ge=0)
    error_mw: float
    actual_mw: float
    forecast_mw: float


class WorstDay(_StrictModel):
    date_utc: str
    pair_count: int = Field(ge=1)
    mae_mw: float = Field(ge=0)


class TimestampSensitivity(_StrictModel):
    shift_hours: Literal[-1, 0, 1]
    pair_count: int = Field(ge=0)
    mae_mw: float | None = Field(default=None, ge=0)
    bias_mw: float | None = None

    @model_validator(mode="after")
    def _empty_values_are_null(self) -> "TimestampSensitivity":
        if self.pair_count == 0 and (self.mae_mw is not None or self.bias_mw is not None):
            raise ValueError("empty sensitivity row must have null metrics")
        if self.pair_count > 0 and (self.mae_mw is None or self.bias_mw is None):
            raise ValueError("non-empty sensitivity row must have metrics")
        return self


class AdditionalMetrics(_StrictModel):
    p90_absolute_error_mw: float | None = Field(default=None, ge=0)
    p95_absolute_error_mw: float | None = Field(default=None, ge=0)
    largest_miss: LargestMiss | None
    scatter_peak_caption: str | None = None
    naive_previous_day_baseline: NaiveBaseline
    mae_reduction_vs_naive_percent: float | None = None
    by_lead_time_bucket: list[LeadTimeErrorGroup]
    by_hour_of_day: list[HourOfDayErrorGroup]
    hour_of_day_mae_extremes: HourOfDayMaeExtremes
    worst_days_by_mae: list[WorstDay] = Field(max_length=5)
    timestamp_sensitivity: list[TimestampSensitivity]


LEAD_TIME_BUCKET_KEYS = frozenset(
    {"<6h", "6-12h", "12-18h", "18-24h", "24-30h", "30-36h", "36-40h", ">=40h"}
)


class LeadTimeSummary(_StrictModel):
    count: int = Field(ge=0)
    min_hours: float | None = None
    median_hours: float | None = None
    mean_hours: float | None = None
    max_hours: float | None = None
    p05_hours: float | None = None
    p95_hours: float | None = None
    buckets: dict[str, int] | None = None

    @model_validator(mode="after")
    def _distribution_matches_count(self) -> "LeadTimeSummary":
        detail = (
            self.min_hours,
            self.median_hours,
            self.mean_hours,
            self.max_hours,
            self.p05_hours,
            self.p95_hours,
            self.buckets,
        )
        if self.count == 0:
            if any(value is not None for value in detail):
                raise ValueError("lead-time detail must be null when count is 0")
            return self

        if any(value is None for value in detail):
            raise ValueError("lead-time detail is required when count is greater than 0")

        assert self.buckets is not None
        if set(self.buckets) != LEAD_TIME_BUCKET_KEYS:
            raise ValueError("lead-time buckets must use the documented bucket keys")
        if any(value < 0 for value in self.buckets.values()):
            raise ValueError("lead-time bucket counts cannot be negative")
        if sum(self.buckets.values()) != self.count:
            raise ValueError("lead-time bucket counts must sum to count")
        if not (self.min_hours <= self.median_hours <= self.max_hours):  # type: ignore[operator]
            raise ValueError("lead-time min/median/max are out of order")
        return self


class AuditEntry(BaseModel):
    """One audit row.

    Entries differ by category (a conflict carries the competing values, a
    missing forecast carries its cutoff), so unknown keys are preserved rather
    than rejected. Every entry must still identify a target and a reason.
    """

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    targetStart: UtcTimestamp
    reason: str


class Audit(_StrictModel):
    missing_forecast: list[AuditEntry]
    missing_actual: list[AuditEntry]
    conflicting_latest_publications: list[AuditEntry]
    unavailable_hourly_actuals: list[AuditEntry]


# --------------------------------------------------------------------------
# Full report
# --------------------------------------------------------------------------


class AnalysisReport(_StrictModel):
    generated_at: UtcTimestamp
    analysis_window: AnalysisWindow
    cutoff_assumption: CutoffAssumption
    period_labelling: str
    sources: Sources
    counts: Counts
    metrics: Metrics
    headline_metrics: HeadlineMetrics
    additional_metrics: AdditionalMetrics
    metric_definitions: dict[str, str]
    lead_time_hours: LeadTimeSummary
    audit: Audit
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _sections_agree(self) -> "AnalysisReport":
        """Cross-check the report's own counts before serving it."""
        counts = self.counts
        window = self.analysis_window

        if counts.valid_hourly_actuals + counts.unavailable_hourly_actuals != window.expected_hours:
            raise ValueError("hourly actual counts do not add up to the expected hours")

        if (
            counts.selected_forecasts
            + counts.missing_forecasts
            + counts.conflicting_latest_publications
            != window.expected_hours
        ):
            raise ValueError("forecast selection counts do not add up to the expected hours")

        if counts.valid_aligned_pairs != self.metrics.pair_count:
            raise ValueError("valid_aligned_pairs and metrics.pair_count disagree")

        if self.metrics.pair_count == 0:
            if any(
                value is not None
                for value in (
                    self.headline_metrics.overforecast_share_percent,
                    self.headline_metrics.rmse_after_bias_mw,
                    self.headline_metrics.bias_squared_error_share_percent,
                    self.headline_metrics.bias_percent_of_mean_actual,
                )
            ):
                raise ValueError("headline metrics must be null when pair_count is 0")
        elif any(
            value is None
            for value in (
                self.headline_metrics.overforecast_share_percent,
                self.headline_metrics.rmse_after_bias_mw,
                self.headline_metrics.bias_squared_error_share_percent,
            )
        ):
            raise ValueError("headline metrics must be present when pair_count is greater than 0")

        additional = self.additional_metrics
        if additional.p90_absolute_error_mw is not None and additional.p95_absolute_error_mw is not None:
            if additional.p90_absolute_error_mw > additional.p95_absolute_error_mw:
                raise ValueError("absolute-error percentiles must be ordered")
        if additional.naive_previous_day_baseline.pair_count > self.metrics.pair_count:
            raise ValueError("naive baseline cannot have more pairs than the model")
        if len(additional.by_lead_time_bucket) and sum(
            row.pair_count for row in additional.by_lead_time_bucket
        ) != self.metrics.pair_count:
            raise ValueError("lead-time error groups do not sum to pair_count")
        if len(additional.by_hour_of_day) and sum(
            row.pair_count for row in additional.by_hour_of_day
        ) != self.metrics.pair_count:
            raise ValueError("hour-of-day error groups do not sum to pair_count")
        if {row.shift_hours for row in additional.timestamp_sensitivity} != {-1, 0, 1}:
            raise ValueError("timestamp sensitivity must include -1h, 0h and +1h")

        if counts.actual_source_records != self.sources.actuals.records:
            raise ValueError("actual source record count disagrees with sources.actuals")

        if counts.forecast_versions_for_january_targets != self.sources.forecasts.versions:
            raise ValueError("forecast version count disagrees with sources.forecasts")

        if counts.forecast_targets != self.sources.forecasts.targets:
            raise ValueError("forecast target count disagrees with sources.forecasts")

        if self.lead_time_hours.count != counts.selected_forecasts:
            raise ValueError("lead-time count disagrees with selected_forecasts")

        audit = self.audit
        if len(audit.conflicting_latest_publications) != counts.conflicting_latest_publications:
            raise ValueError("conflict audit rows disagree with the conflict count")

        if len(audit.unavailable_hourly_actuals) != counts.unavailable_hourly_actuals:
            raise ValueError("unavailable-actual audit rows disagree with the count")

        if len(audit.missing_actual) != counts.missing_actuals_for_selected_forecasts:
            raise ValueError("missing-actual audit rows disagree with the count")

        if len(audit.missing_forecast) < counts.missing_forecasts:
            raise ValueError("missing-forecast audit rows are fewer than the count")

        expected_unmatched = (
            len(audit.missing_forecast) + len(audit.missing_actual) + len(audit.conflicting_latest_publications)
        )
        if counts.unmatched_targets != expected_unmatched:
            raise ValueError("unmatched_targets disagrees with the audit rows")

        return self


# --------------------------------------------------------------------------
# Summary endpoint
# --------------------------------------------------------------------------


class AnalysisSummary(_StrictModel):
    """The report without the row-level audit lists.

    Everything needed to interpret the metrics is included: window, cutoff
    assumption, period labelling, counts, metrics, lead-time distribution and
    limitations. The audit lists live on ``/api/analysis/report``.
    """

    generated_at: UtcTimestamp
    analysis_window: AnalysisWindow
    cutoff_assumption: CutoffAssumption
    period_labelling: str
    counts: Counts
    metrics: Metrics
    headline_metrics: HeadlineMetrics
    additional_metrics: AdditionalMetrics
    lead_time_hours: LeadTimeSummary
    limitations: list[str] = Field(min_length=1)


# --------------------------------------------------------------------------
# Aligned observations
# --------------------------------------------------------------------------


class AlignedRecord(_StrictModel):
    targetStart: UtcTimestamp
    actualMW: float
    forecastMW: float
    errorMW: float
    forecastPublishTime: UtcTimestamp
    leadHours: float


class AlignedDataset(_StrictModel):
    dataset: str
    description: str
    derived: bool
    pair_count: int = Field(ge=0)
    records: list[AlignedRecord]

    @model_validator(mode="after")
    def _records_are_consistent(self) -> "AlignedDataset":
        if len(self.records) != self.pair_count:
            raise ValueError("pair_count does not match the number of records")

        for index, record in enumerate(self.records):
            # The producer rounds to 3 decimals, so allow half a unit there.
            if abs((record.forecastMW - record.actualMW) - record.errorMW) > 0.002:
                raise ValueError(f"record {index}: errorMW is not forecastMW - actualMW")

            expected_lead = (
                parse_utc(record.targetStart) - parse_utc(record.forecastPublishTime)
            ).total_seconds() / 3600.0
            if abs(expected_lead - record.leadHours) > 0.002:
                raise ValueError(f"record {index}: leadHours does not match the timestamps")

        return self


class AlignedAnalysisResponse(_StrictModel):
    """One page of aligned observations plus enough context to walk them."""

    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    count: int = Field(ge=0)
    hasMore: bool
    records: list[AlignedRecord]


__all__ = [
    "AlignedAnalysisResponse",
    "AlignedDataset",
    "AlignedRecord",
    "AnalysisReport",
    "AnalysisSummary",
    "AdditionalMetrics",
    "Audit",
    "AuditEntry",
    "Counts",
    "ErrorGroup",
    "HeadlineMetrics",
    "HourOfDayErrorGroup",
    "LargestMiss",
    "LeadTimeErrorGroup",
    "Metrics",
    "NaiveBaseline",
    "TimestampSensitivity",
    "WorstDay",
]
