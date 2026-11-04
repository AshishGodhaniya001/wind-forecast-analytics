"""Read the generated January 2026 analysis artefacts from disk.

The API never calls Elexon and never recomputes metrics. It loads the files
written by ``scripts/analyse_january_data.py``, validates them against the
typed models, and serves the result.

Paths are fixed. Nothing in a request can influence which file is read.

Errors are split so the HTTP layer can respond honestly:

* :class:`AnalysisDataMissing` - the artefact has not been generated (503).
* :class:`AnalysisDataInvalid` - the artefact exists but cannot be trusted (500).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.analysis import AlignedDataset, AnalysisReport

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BACKEND_ROOT / "data" / "processed"

REPORT_FILENAME = "analysis_report_january_2026.json"
ALIGNED_FILENAME = "aligned_analysis_january_2026.json"

# Shown to API clients instead of an absolute server path.
DOCUMENTED_DATA_LOCATION = "backend/data/processed"


class AnalysisDataError(RuntimeError):
    """Base class for problems with the generated analysis artefacts."""

    code = "analysis_data_unavailable"
    status_code = 503

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AnalysisDataMissing(AnalysisDataError):
    """The required artefact has not been generated yet."""

    code = "analysis_data_missing"
    status_code = 503


class AnalysisDataInvalid(AnalysisDataError):
    """The artefact exists but is malformed, incomplete or self-contradictory."""

    code = "analysis_data_invalid"
    status_code = 500


def _summarise_validation_error(exc: ValidationError, *, limit: int = 5) -> str:
    """Render a short, payload-free description of a schema failure."""
    errors = exc.errors()
    parts = []
    for error in errors[:limit]:
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    if len(errors) > limit:
        parts.append(f"... and {len(errors) - limit} more")
    return "; ".join(parts)


class AnalysisStore:
    """Loads and validates the fixed analysis artefacts."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR

    def _read_json(self, filename: str) -> object:
        path = self._data_dir / filename

        if not path.is_file():
            raise AnalysisDataMissing(
                f"Analysis output {filename!r} was not found in "
                f"{DOCUMENTED_DATA_LOCATION}. Run "
                "'python scripts/analyse_january_data.py' from the backend "
                "directory to generate it."
            )

        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError as exc:
            raise AnalysisDataInvalid(
                f"Analysis output {filename!r} is not valid JSON "
                f"(line {exc.lineno}, column {exc.colno}: {exc.msg})."
            ) from exc
        except OSError as exc:
            raise AnalysisDataMissing(
                f"Analysis output {filename!r} could not be read: "
                f"{exc.strerror or 'unknown error'}."
            ) from exc

    def load_report(self) -> AnalysisReport:
        """Return the validated analysis report."""
        payload = self._read_json(REPORT_FILENAME)
        try:
            return AnalysisReport.model_validate(payload)
        except ValidationError as exc:
            raise AnalysisDataInvalid(
                f"Analysis output {REPORT_FILENAME!r} does not match the expected "
                f"report schema: {_summarise_validation_error(exc)}. Re-run the "
                "analysis script to regenerate it."
            ) from exc

    def load_aligned(self) -> AlignedDataset:
        """Return validated aligned pairs, cross-checked against the report."""
        payload = self._read_json(ALIGNED_FILENAME)
        try:
            aligned = AlignedDataset.model_validate(payload)
        except ValidationError as exc:
            raise AnalysisDataInvalid(
                f"Analysis output {ALIGNED_FILENAME!r} does not match the expected "
                f"aligned-pairs schema: {_summarise_validation_error(exc)}. Re-run "
                "the analysis script to regenerate it."
            ) from exc

        # The two artefacts are written together. If they disagree, one of them
        # is stale and neither can be served as a coherent result.
        report = self.load_report()
        if aligned.pair_count != report.metrics.pair_count:
            raise AnalysisDataInvalid(
                "Analysis outputs are inconsistent: the aligned file contains "
                f"{aligned.pair_count} pairs but the report scores "
                f"{report.metrics.pair_count}. Re-run the analysis script."
            )
        if aligned.pair_count != report.counts.valid_aligned_pairs:
            raise AnalysisDataInvalid(
                "Analysis outputs are inconsistent: the aligned file contains "
                f"{aligned.pair_count} pairs but the report counts "
                f"{report.counts.valid_aligned_pairs} valid pairs. Re-run the "
                "analysis script."
            )
        return aligned


def get_analysis_store() -> AnalysisStore:
    """FastAPI dependency returning a store rooted at the fixed data directory.

    Tests override this dependency with a temporary directory. Request
    parameters are never used to build the path.
    """
    return AnalysisStore()


__all__ = [
    "ALIGNED_FILENAME",
    "AnalysisDataError",
    "AnalysisDataInvalid",
    "AnalysisDataMissing",
    "AnalysisStore",
    "DEFAULT_DATA_DIR",
    "REPORT_FILENAME",
    "get_analysis_store",
]
