"""Read-only endpoints exposing the generated January 2026 analysis.

Three endpoints:

* ``GET /api/analysis/summary``  - metrics, counts, cutoff, limitations.
* ``GET /api/analysis/aligned``  - paginated aligned forecast/actual pairs.
* ``GET /api/analysis/report``   - the full audit report, including row-level
  audit lists that the summary omits.

All three read the same generated artefacts. None of them call Elexon or
recompute metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.analysis import (
    AlignedAnalysisResponse,
    AnalysisReport,
    AnalysisSummary,
)
from app.services.analysis_store import (
    AnalysisDataError,
    AnalysisStore,
    get_analysis_store,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

DEFAULT_ALIGNED_LIMIT = 200
MAX_ALIGNED_LIMIT = 1000


def _http_error(exc: AnalysisDataError) -> HTTPException:
    """Translate a data problem into a clear HTTP response."""
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get(
    "/summary",
    response_model=AnalysisSummary,
    summary="January 2026 forecast accuracy summary",
    description=(
        "Metrics, data-quality counts, the provisional forecast cutoff rule, "
        "the lead-time distribution and the documented limitations. Values are "
        "read from the generated analysis report and are not recalculated."
    ),
)
def get_analysis_summary(
    store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisSummary:
    try:
        report = store.load_report()
    except AnalysisDataError as exc:
        raise _http_error(exc) from exc

    return AnalysisSummary(
        generated_at=report.generated_at,
        analysis_window=report.analysis_window,
        cutoff_assumption=report.cutoff_assumption,
        period_labelling=report.period_labelling,
        counts=report.counts,
        metrics=report.metrics,
        headline_metrics=report.headline_metrics,
        additional_metrics=report.additional_metrics,
        lead_time_hours=report.lead_time_hours,
        limitations=report.limitations,
    )


@router.get(
    "/aligned",
    response_model=AlignedAnalysisResponse,
    summary="Aligned forecast and actual observations",
    description=(
        "The actual aligned pairs produced by the analysis, ordered by target "
        "hour. Pagination is explicit: `total` is always the full number of "
        "pairs, so no records are hidden. `limit` defaults to 200 and is capped "
        "at 1000; `offset` is zero-based. An offset at or beyond `total` "
        "returns an empty page with `hasMore: false`."
    ),
)
def get_aligned_analysis(
    limit: int = Query(
        DEFAULT_ALIGNED_LIMIT,
        ge=1,
        le=MAX_ALIGNED_LIMIT,
        description="Maximum number of records to return (1-1000).",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Zero-based index of the first record to return.",
    ),
    store: AnalysisStore = Depends(get_analysis_store),
) -> AlignedAnalysisResponse:
    try:
        aligned = store.load_aligned()
    except AnalysisDataError as exc:
        raise _http_error(exc) from exc

    total = aligned.pair_count
    page = aligned.records[offset : offset + limit]

    return AlignedAnalysisResponse(
        total=total,
        limit=limit,
        offset=offset,
        count=len(page),
        hasMore=offset + len(page) < total,
        records=page,
    )


@router.get(
    "/report",
    response_model=AnalysisReport,
    summary="Full analysis report with audit lists",
    description=(
        "The complete generated report: metrics and definitions, sources, "
        "period labelling, lead-time distribution, limitations and the "
        "row-level audit lists (missing forecasts, missing actuals, conflicting "
        "publications, unavailable hourly actuals) that the summary omits."
    ),
)
def get_analysis_report(
    store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisReport:
    try:
        return store.load_report()
    except AnalysisDataError as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
