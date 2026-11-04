"""HTTP client for the official Elexon BMRS Insights API.

Only the two datasets required by the challenge are supported:

* ``FUELHH``  - half-hourly generation outturn by fuel type (actuals)
* ``WINDFOR`` - wind generation forecast

Verified API behaviour (checked against the live API and the official OpenAPI
specification at https://data.elexon.co.uk/swagger/v1/swagger.json):

1. ``publishDateTimeFrom`` and ``publishDateTimeTo`` are **inclusive** at both
   ends. Requesting a single instant returns the record published at that
   instant; requesting one second earlier returns nothing.
2. ``WINDFOR`` **ignores** ``startTimeFrom`` / ``startTimeTo``. Target-time
   filtering has to be done by the caller (see ``data_validation``).
3. ``WINDFOR`` without a publish window returns only the **latest published**
   version of each forecast. A publish window is therefore always sent, so all
   historical versions are retrieved and no look-ahead is baked in.
4. The ``/stream`` endpoints have no 7-day range limit; the non-stream
   ``/datasets/...`` endpoints reject ranges longer than 7 days with HTTP 400.

The client never fabricates data: an unreachable API or an unexpected payload
raises :class:`ElexonAPIError`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 2.0

# A misconfigured Retry-After must not stall the process indefinitely.
MAX_RETRY_AFTER_SECONDS = 60.0

FUELHH_PATH = "/datasets/FUELHH/stream"
WINDFOR_PATH = "/datasets/WINDFOR/stream"

# Status codes worth retrying. Everything else fails immediately.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

USER_AGENT = "wind-forecast-analytics/0.1 (internship challenge)"


class ElexonAPIError(RuntimeError):
    """Elexon was unreachable, or returned a response we cannot use."""


def _retry_after_seconds(header_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header expressed in seconds.

    The HTTP-date form is intentionally not interpreted; ``None`` falls back to
    exponential backoff.
    """
    if not header_value:
        return None
    try:
        return max(0.0, float(header_value.strip()))
    except ValueError:
        return None


def _utc_parameter(value: datetime) -> str:
    """Format a datetime as the ``YYYY-MM-DDTHH:MM:SSZ`` form Elexon expects."""
    if value.tzinfo is None:
        raise ValueError("datetime parameters must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ElexonClient:
    """Thin, retrying client for the two Elexon endpoints we need."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            transport=transport,
        )

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ElexonClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals --------------------------------------------------------

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff for the given 1-based attempt number."""
        return self.backoff_seconds * (2 ** (attempt - 1))

    def _get(self, path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        last_error = "no attempt was made"

        for attempt in range(1, self.max_attempts + 1):
            delay: float | None = None

            try:
                response = self._client.get(path, params=dict(params))
            except httpx.TimeoutException:
                last_error = f"request to {path} timed out"
                delay = self._backoff(attempt)
            except httpx.HTTPError as exc:
                last_error = f"transport error calling {path}: {exc}"
                delay = self._backoff(attempt)
            else:
                if response.status_code == 200:
                    payload = self._parse_payload(response, path)
                    logger.info(
                        "GET %s -> HTTP %s, %d record(s)",
                        response.request.url,
                        response.status_code,
                        len(payload),
                    )
                    return payload

                body = response.text[:300].strip() or "<empty body>"
                last_error = f"HTTP {response.status_code} from {path}: {body}"

                if response.status_code not in RETRYABLE_STATUS_CODES:
                    # 4xx (other than 429) means our request is wrong. Retrying
                    # would only repeat the same mistake.
                    raise ElexonAPIError(last_error)

                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                delay = retry_after if retry_after is not None else self._backoff(attempt)

            if attempt >= self.max_attempts or delay is None:
                break

            delay = min(delay, MAX_RETRY_AFTER_SECONDS)
            logger.warning(
                "%s; retrying in %.1fs (attempt %d/%d)",
                last_error,
                delay,
                attempt,
                self.max_attempts,
            )
            self._sleep(delay)

        raise ElexonAPIError(
            f"Elexon request failed after {self.max_attempts} attempt(s): {last_error}"
        )

    @staticmethod
    def _parse_payload(response: httpx.Response, path: str) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ElexonAPIError(
                f"{path} returned a body that is not valid JSON: {exc}"
            ) from exc

        if not isinstance(payload, list):
            raise ElexonAPIError(
                f"{path} returned a JSON {type(payload).__name__}, "
                "expected a list of records"
            )

        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ElexonAPIError(
                    f"{path} record {index} is a JSON {type(item).__name__}, "
                    "expected an object"
                )

        return payload

    # -- public API -------------------------------------------------------

    def fetch_fuelhh_wind(
        self, publish_from: datetime, publish_to: datetime
    ) -> list[dict[str, Any]]:
        """Fetch raw FUELHH actual-generation records for fuel type WIND.

        Returns the records exactly as Elexon sent them, newest publication
        first. No validation or filtering happens here.
        """
        if publish_to < publish_from:
            raise ValueError("publish_to must not be earlier than publish_from")

        params = {
            "publishDateTimeFrom": _utc_parameter(publish_from),
            "publishDateTimeTo": _utc_parameter(publish_to),
            "fuelType": "WIND",
        }
        return self._get(FUELHH_PATH, params)

    def fetch_windfor(
        self, publish_from: datetime, publish_to: datetime
    ) -> list[dict[str, Any]]:
        """Fetch raw WINDFOR forecast records for a publication window.

        A publication window is always sent: omitting it makes the API return
        only the latest published version of each forecast, which would hide
        historical versions and introduce look-ahead bias.
        """
        if publish_to < publish_from:
            raise ValueError("publish_to must not be earlier than publish_from")

        params = {
            "publishDateTimeFrom": _utc_parameter(publish_from),
            "publishDateTimeTo": _utc_parameter(publish_to),
        }
        return self._get(WINDFOR_PATH, params)
