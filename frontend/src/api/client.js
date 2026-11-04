/**
 * API client for the Wind Forecast Analytics backend.
 *
 * The dashboard never computes metrics. It reads the reviewed artefacts that
 * the FastAPI service exposes and validates their shape before rendering. If a
 * response is missing, unreachable or malformed, the caller receives a typed
 * error and the UI shows an honest failure state - no mock data, no zeros.
 */

const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const ALIGNED_PAGE_SIZE = 500
const MAX_ALIGNED_PAGES = 20

const COUNT_KEYS = [
  'actual_source_records',
  'valid_hourly_actuals',
  'unavailable_hourly_actuals',
  'forecast_versions_for_january_targets',
  'forecast_targets',
  'selected_forecasts',
  'missing_forecasts',
  'conflicting_latest_publications',
  'collapsed_duplicate_publications',
  'missing_actuals_for_selected_forecasts',
  'unmatched_targets',
  'valid_aligned_pairs',
]

const METRIC_KEYS = [
  'mae_mw',
  'rmse_mw',
  'bias_mw',
  'mean_actual_mw',
  'mean_forecast_mw',
]

const AUDIT_KEYS = [
  'missing_forecast',
  'missing_actual',
  'conflicting_latest_publications',
  'unavailable_hourly_actuals',
]

export class ApiError extends Error {
  constructor(message, { status = null, code = null, cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.cause = cause
  }
}

export class MalformedResponseError extends Error {
  constructor(message) {
    super(message)
    this.name = 'MalformedResponseError'
  }
}

/** Resolve the backend origin, allowing an empty value to mean same-origin. */
export function resolveApiBaseUrl(env) {
  const configured = env?.VITE_API_BASE_URL
  const raw = configured === undefined ? DEFAULT_API_BASE_URL : configured
  return String(raw).trim().replace(/\/+$/, '')
}

export function getApiBaseUrl() {
  return resolveApiBaseUrl(import.meta.env)
}

// --------------------------------------------------------------------------
// Shape validation
// --------------------------------------------------------------------------

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function fail(path, expectation) {
  throw new MalformedResponseError(
    `The API response is missing or has an invalid ${path}; expected ${expectation}.`,
  )
}

function requireObject(value, path) {
  if (!isPlainObject(value)) fail(path, 'an object')
  return value
}

function requireArray(value, path) {
  if (!Array.isArray(value)) fail(path, 'an array')
  return value
}

function requireString(value, path) {
  if (typeof value !== 'string' || value.length === 0) fail(path, 'a non-empty string')
  return value
}

function requireBoolean(value, path) {
  if (typeof value !== 'boolean') fail(path, 'a boolean')
  return value
}

function requireFiniteNumber(value, path) {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(path, 'a finite number')
  return value
}

function requireNullableNumber(value, path) {
  if (value !== null && (typeof value !== 'number' || !Number.isFinite(value))) {
    fail(path, 'a finite number or null')
  }
  return value
}

function requireNonNegativeInteger(value, path) {
  if (!Number.isInteger(value) || value < 0) fail(path, 'a non-negative integer')
  return value
}

function requirePositiveInteger(value, path) {
  if (!Number.isInteger(value) || value <= 0) fail(path, 'a positive integer')
  return value
}

function requireUtcTimestamp(value, path) {
  requireString(value, path)
  if (Number.isNaN(Date.parse(value))) fail(path, 'an ISO-8601 timestamp')
  return value
}

function validateLeadTimeSummary(value, path) {
  const lead = requireObject(value, path)
  requireNonNegativeInteger(lead.count, `${path}.count`)

  const detailKeys = [
    'min_hours',
    'median_hours',
    'mean_hours',
    'max_hours',
    'p05_hours',
    'p95_hours',
  ]

  if (lead.count === 0) {
    detailKeys.forEach((key) => {
      if (lead[key] !== null && lead[key] !== undefined) {
        fail(`${path}.${key}`, 'null when count is 0')
      }
    })
    if (lead.buckets !== null && lead.buckets !== undefined) {
      fail(`${path}.buckets`, 'null when count is 0')
    }
    return lead
  }

  detailKeys.forEach((key) => requireFiniteNumber(lead[key], `${path}.${key}`))
  const buckets = requireObject(lead.buckets, `${path}.buckets`)
  Object.entries(buckets).forEach(([key, count]) => {
    requireNonNegativeInteger(count, `${path}.buckets.${key}`)
  })

  return lead
}

function validateHeadlineMetrics(value, path, pairCount) {
  const headline = requireObject(value, path)
  const percentKeys = [
    'overforecast_share_percent',
    'bias_squared_error_share_percent',
    'bias_percent_of_mean_actual',
  ]
  percentKeys.forEach((key) =>
    requireNullableNumber(headline[key], `${path}.${key}`),
  )
  requireNullableNumber(headline.rmse_after_bias_mw, `${path}.rmse_after_bias_mw`)
  requireString(headline.headline_text, `${path}.headline_text`)

  if (pairCount === 0) {
    if (
      percentKeys.some((key) => headline[key] !== null) ||
      headline.rmse_after_bias_mw !== null
    ) {
      fail(path, 'null calculations when pair_count is 0')
    }
  } else if (
    headline.overforecast_share_percent === null ||
    headline.bias_squared_error_share_percent === null ||
    headline.rmse_after_bias_mw === null
  ) {
    fail(path, 'calculated values when pair_count is greater than 0')
  }

  if (
    headline.overforecast_share_percent !== null &&
    (headline.overforecast_share_percent < 0 || headline.overforecast_share_percent > 100)
  ) {
    fail(`${path}.overforecast_share_percent`, 'a percentage from 0 to 100')
  }
  if (
    headline.bias_squared_error_share_percent !== null &&
    (headline.bias_squared_error_share_percent < 0 || headline.bias_squared_error_share_percent > 100)
  ) {
    fail(`${path}.bias_squared_error_share_percent`, 'a percentage from 0 to 100')
  }

  return headline
}

function validateAdditionalMetrics(value, path, pairCount) {
  const metrics = requireObject(value, path)
  requireNullableNumber(metrics.p90_absolute_error_mw, `${path}.p90_absolute_error_mw`)
  requireNullableNumber(metrics.p95_absolute_error_mw, `${path}.p95_absolute_error_mw`)
  if (metrics.scatter_peak_caption === null) {
    if (pairCount > 0) fail(`${path}.scatter_peak_caption`, 'a caption for non-empty aligned data')
  } else {
    requireString(metrics.scatter_peak_caption, `${path}.scatter_peak_caption`)
  }
  if (metrics.largest_miss !== null) {
    const miss = requireObject(metrics.largest_miss, `${path}.largest_miss`)
    requireUtcTimestamp(miss.target_start, `${path}.largest_miss.target_start`)
    requireString(miss.date_utc, `${path}.largest_miss.date_utc`)
    requireNonNegativeInteger(miss.hour_utc, `${path}.largest_miss.hour_utc`)
    requireFiniteNumber(miss.absolute_error_mw, `${path}.largest_miss.absolute_error_mw`)
    requireFiniteNumber(miss.error_mw, `${path}.largest_miss.error_mw`)
    requireFiniteNumber(miss.actual_mw, `${path}.largest_miss.actual_mw`)
    requireFiniteNumber(miss.forecast_mw, `${path}.largest_miss.forecast_mw`)
  }

  const baseline = requireObject(
    metrics.naive_previous_day_baseline,
    `${path}.naive_previous_day_baseline`,
  )
  requireNonNegativeInteger(baseline.pair_count, `${path}.naive_previous_day_baseline.pair_count`)
  requireNullableNumber(baseline.mae_mw, `${path}.naive_previous_day_baseline.mae_mw`)
  requireNullableNumber(baseline.rmse_mw, `${path}.naive_previous_day_baseline.rmse_mw`)
  requireNullableNumber(metrics.mae_reduction_vs_naive_percent, `${path}.mae_reduction_vs_naive_percent`)
  if (baseline.pair_count > pairCount) fail(`${path}.naive_previous_day_baseline.pair_count`, 'no more than the model pair count')
  if ((baseline.pair_count === 0) !== (baseline.mae_mw === null && baseline.rmse_mw === null)) {
    fail(`${path}.naive_previous_day_baseline`, 'metrics consistent with pair_count')
  }

  const leadGroups = requireArray(metrics.by_lead_time_bucket, `${path}.by_lead_time_bucket`)
  const leadBucketNames = ['<6h', '6-12h', '12-18h', '18-24h', '24-30h', '30-36h', '36-40h', '>=40h']
  if (leadGroups.length !== leadBucketNames.length) fail(`${path}.by_lead_time_bucket`, 'the eight documented buckets')
  let leadCount = 0
  leadGroups.forEach((item, index) => {
    const row = requireObject(item, `${path}.by_lead_time_bucket[${index}]`)
    requireString(row.bucket, `${path}.by_lead_time_bucket[${index}].bucket`)
    if (row.bucket !== leadBucketNames[index]) fail(`${path}.by_lead_time_bucket[${index}].bucket`, leadBucketNames[index])
    leadCount += validateErrorGroup(row, `${path}.by_lead_time_bucket[${index}]`)
  })
  if (leadCount !== pairCount) fail(`${path}.by_lead_time_bucket`, 'groups summing to pair_count')

  const hourGroups = requireArray(metrics.by_hour_of_day, `${path}.by_hour_of_day`)
  if (hourGroups.length !== 24) fail(`${path}.by_hour_of_day`, '24 UTC hour groups')
  let hourCount = 0
  hourGroups.forEach((item, index) => {
    const row = requireObject(item, `${path}.by_hour_of_day[${index}]`)
    if (row.hour_utc !== index) fail(`${path}.by_hour_of_day[${index}].hour_utc`, String(index))
    hourCount += validateErrorGroup(row, `${path}.by_hour_of_day[${index}]`)
  })
  if (hourCount !== pairCount) fail(`${path}.by_hour_of_day`, 'groups summing to pair_count')

  const extremes = requireObject(metrics.hour_of_day_mae_extremes, `${path}.hour_of_day_mae_extremes`)
  for (const kind of ['highest', 'lowest']) {
    const hour = extremes[`${kind}_hour_utc`]
    const mae = extremes[`${kind}_mae_mw`]
    if (hour === null || hour === undefined) {
      if (mae !== null) fail(`${path}.hour_of_day_mae_extremes.${kind}`, 'hour and MAE both null or both present')
      if (pairCount > 0) fail(`${path}.hour_of_day_mae_extremes.${kind}`, 'a populated hour for non-empty data')
      continue
    }
    requireNonNegativeInteger(hour, `${path}.hour_of_day_mae_extremes.${kind}_hour_utc`)
    if (hour > 23) fail(`${path}.hour_of_day_mae_extremes.${kind}_hour_utc`, 'an hour from 0 to 23')
    requireFiniteNumber(mae, `${path}.hour_of_day_mae_extremes.${kind}_mae_mw`)
    if (hourCount === 0 || hourGroups[hour]?.mae_mw !== mae) {
      fail(`${path}.hour_of_day_mae_extremes.${kind}`, 'an MAE matching its grouped UTC hour')
    }
  }

  const worstDays = requireArray(metrics.worst_days_by_mae, `${path}.worst_days_by_mae`)
  if (worstDays.length > 5) fail(`${path}.worst_days_by_mae`, 'at most five days')
  worstDays.forEach((item, index) => {
    const row = requireObject(item, `${path}.worst_days_by_mae[${index}]`)
    requireString(row.date_utc, `${path}.worst_days_by_mae[${index}].date_utc`)
    requirePositiveInteger(row.pair_count, `${path}.worst_days_by_mae[${index}].pair_count`)
    requireFiniteNumber(row.mae_mw, `${path}.worst_days_by_mae[${index}].mae_mw`)
  })

  const sensitivity = requireArray(metrics.timestamp_sensitivity, `${path}.timestamp_sensitivity`)
  if (sensitivity.length !== 3) fail(`${path}.timestamp_sensitivity`, 'three timestamp shifts')
  sensitivity.forEach((item, index) => {
    const row = requireObject(item, `${path}.timestamp_sensitivity[${index}]`)
    if (row.shift_hours !== index - 1) fail(`${path}.timestamp_sensitivity[${index}].shift_hours`, String(index - 1))
    requireNonNegativeInteger(row.pair_count, `${path}.timestamp_sensitivity[${index}].pair_count`)
    requireNullableNumber(row.mae_mw, `${path}.timestamp_sensitivity[${index}].mae_mw`)
    requireNullableNumber(row.bias_mw, `${path}.timestamp_sensitivity[${index}].bias_mw`)
  })

  if (pairCount === 0 && (metrics.p90_absolute_error_mw !== null || metrics.p95_absolute_error_mw !== null || metrics.largest_miss !== null)) {
    fail(path, 'null miss statistics when pair_count is 0')
  }
  if (pairCount > 0 && (metrics.p90_absolute_error_mw === null || metrics.p95_absolute_error_mw === null || metrics.largest_miss === null)) {
    fail(path, 'miss statistics when pair_count is greater than 0')
  }
  return metrics
}

function validateErrorGroup(row, path) {
  requireNonNegativeInteger(row.pair_count, `${path}.pair_count`)
  requireNullableNumber(row.mae_mw, `${path}.mae_mw`)
  requireNullableNumber(row.bias_mw, `${path}.bias_mw`)
  if ((row.pair_count === 0) !== (row.mae_mw === null && row.bias_mw === null)) {
    fail(path, 'metrics consistent with pair_count')
  }
  return row.pair_count
}

export function validateSummary(payload) {
  const summary = requireObject(payload, 'summary')
  requireUtcTimestamp(summary.generated_at, 'summary.generated_at')

  const window = requireObject(summary.analysis_window, 'summary.analysis_window')
  requireUtcTimestamp(window.start, 'summary.analysis_window.start')
  requireUtcTimestamp(window.end, 'summary.analysis_window.end')
  requireString(window.timezone, 'summary.analysis_window.timezone')
  requireNonNegativeInteger(window.expected_hours, 'summary.analysis_window.expected_hours')

  const cutoff = requireObject(summary.cutoff_assumption, 'summary.cutoff_assumption')
  requireString(cutoff.rule, 'summary.cutoff_assumption.rule')
  requireString(cutoff.status, 'summary.cutoff_assumption.status')
  requireBoolean(
    cutoff.not_prescribed_by_challenge,
    'summary.cutoff_assumption.not_prescribed_by_challenge',
  )
  requireString(cutoff.rationale, 'summary.cutoff_assumption.rationale')

  requireString(summary.period_labelling, 'summary.period_labelling')

  const counts = requireObject(summary.counts, 'summary.counts')
  COUNT_KEYS.forEach((key) => requireNonNegativeInteger(counts[key], `summary.counts.${key}`))

  const metrics = requireObject(summary.metrics, 'summary.metrics')
  requireNonNegativeInteger(metrics.pair_count, 'summary.metrics.pair_count')
  METRIC_KEYS.forEach((key) => requireNullableNumber(metrics[key], `summary.metrics.${key}`))
  requireNullableNumber(metrics.nmae_percent, 'summary.metrics.nmae_percent')

  if (metrics.pair_count === 0) {
    METRIC_KEYS.forEach((key) => {
      if (metrics[key] !== null) fail(`summary.metrics.${key}`, 'null when pair_count is 0')
    })
    if (metrics.nmae_percent !== null) {
      fail('summary.metrics.nmae_percent', 'null when pair_count is 0')
    }
  } else {
    METRIC_KEYS.forEach((key) => requireFiniteNumber(metrics[key], `summary.metrics.${key}`))
    // nMAE is legitimately null when mean actual generation is not positive.
  }

  validateHeadlineMetrics(
    summary.headline_metrics,
    'summary.headline_metrics',
    metrics.pair_count,
  )
  validateAdditionalMetrics(
    summary.additional_metrics,
    'summary.additional_metrics',
    metrics.pair_count,
  )

  validateLeadTimeSummary(summary.lead_time_hours, 'summary.lead_time_hours')

  const limitations = requireArray(summary.limitations, 'summary.limitations')
  limitations.forEach((item, index) =>
    requireString(item, `summary.limitations[${index}]`),
  )
  if (limitations.length === 0) fail('summary.limitations', 'at least one limitation')

  return summary
}

export function validateReport(payload) {
  const report = requireObject(payload, 'report')
  requireUtcTimestamp(report.generated_at, 'report.generated_at')
  requireString(report.period_labelling, 'report.period_labelling')

  const sources = requireObject(report.sources, 'report.sources')
  const actuals = requireObject(sources.actuals, 'report.sources.actuals')
  requireString(actuals.file, 'report.sources.actuals.file')
  requireNonNegativeInteger(actuals.records, 'report.sources.actuals.records')
  requirePositiveInteger(
    actuals.resolution_seconds,
    'report.sources.actuals.resolution_seconds',
  )

  const forecasts = requireObject(sources.forecasts, 'report.sources.forecasts')
  requireString(forecasts.file, 'report.sources.forecasts.file')
  requireNonNegativeInteger(forecasts.versions, 'report.sources.forecasts.versions')
  requireNonNegativeInteger(forecasts.targets, 'report.sources.forecasts.targets')
  requirePositiveInteger(
    forecasts.resolution_seconds,
    'report.sources.forecasts.resolution_seconds',
  )

  const definitions = requireObject(report.metric_definitions, 'report.metric_definitions')
  Object.entries(definitions).forEach(([key, text]) => {
    requireString(text, `report.metric_definitions.${key}`)
  })

  const audit = requireObject(report.audit, 'report.audit')
  AUDIT_KEYS.forEach((key) => {
    const rows = requireArray(audit[key], `report.audit.${key}`)
    rows.forEach((row, index) => {
      const entry = requireObject(row, `report.audit.${key}[${index}]`)
      requireUtcTimestamp(entry.targetStart, `report.audit.${key}[${index}].targetStart`)
      requireString(entry.reason, `report.audit.${key}[${index}].reason`)
    })
  })

  validateLeadTimeSummary(report.lead_time_hours, 'report.lead_time_hours')
  const reportMetrics = requireObject(report.metrics, 'report.metrics')
  requireNonNegativeInteger(reportMetrics.pair_count, 'report.metrics.pair_count')
  validateHeadlineMetrics(
    report.headline_metrics,
    'report.headline_metrics',
    reportMetrics.pair_count,
  )
  validateAdditionalMetrics(
    report.additional_metrics,
    'report.additional_metrics',
    reportMetrics.pair_count,
  )

  const limitations = requireArray(report.limitations, 'report.limitations')
  limitations.forEach((item, index) =>
    requireString(item, `report.limitations[${index}]`),
  )
  if (limitations.length === 0) fail('report.limitations', 'at least one limitation')

  return report
}

function validateAlignedRecord(record, path) {
  const row = requireObject(record, path)
  requireUtcTimestamp(row.targetStart, `${path}.targetStart`)
  requireFiniteNumber(row.actualMW, `${path}.actualMW`)
  requireFiniteNumber(row.forecastMW, `${path}.forecastMW`)
  requireFiniteNumber(row.errorMW, `${path}.errorMW`)
  requireUtcTimestamp(row.forecastPublishTime, `${path}.forecastPublishTime`)
  requireFiniteNumber(row.leadHours, `${path}.leadHours`)

  if (Math.abs(row.forecastMW - row.actualMW - row.errorMW) > 0.002) {
    fail(`${path}.errorMW`, 'forecastMW - actualMW')
  }

  const computedLead =
    (Date.parse(row.targetStart) - Date.parse(row.forecastPublishTime)) / 3_600_000
  if (Math.abs(computedLead - row.leadHours) > 0.002) {
    fail(`${path}.leadHours`, 'the interval between publishTime and targetStart')
  }

  return row
}

export function validateAlignedPage(payload, path = 'aligned') {
  const page = requireObject(payload, path)
  requireNonNegativeInteger(page.total, `${path}.total`)
  requireNonNegativeInteger(page.offset, `${path}.offset`)
  requireNonNegativeInteger(page.count, `${path}.count`)
  requireBoolean(page.hasMore, `${path}.hasMore`)

  const records = requireArray(page.records, `${path}.records`)
  if (records.length !== page.count) {
    fail(`${path}.count`, 'the number of records returned')
  }
  records.forEach((record, index) =>
    validateAlignedRecord(record, `${path}.records[${index}]`),
  )

  return page
}

// --------------------------------------------------------------------------
// HTTP
// --------------------------------------------------------------------------

async function fetchJson(path, { signal } = {}) {
  const baseUrl = getApiBaseUrl()
  let response

  try {
    response = await fetch(`${baseUrl}${path}`, {
      signal,
      headers: { Accept: 'application/json' },
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError(
      `Could not reach the analysis API at ${baseUrl || 'the same origin'}. ` +
        'Check that the backend is running and that the URL is correct.',
      { cause: error },
    )
  }

  let payload = null
  let parseError = null
  try {
    payload = await response.json()
  } catch (error) {
    parseError = error
  }

  if (!response.ok) {
    const detail = payload?.detail
    const message =
      (typeof detail === 'string' && detail) ||
      (detail && typeof detail.message === 'string' && detail.message) ||
      `The analysis API returned HTTP ${response.status}.`
    const code = detail && typeof detail.code === 'string' ? detail.code : null
    throw new ApiError(message, { status: response.status, code })
  }

  if (parseError) {
    throw new MalformedResponseError(
      'The analysis API returned a response that is not valid JSON.',
    )
  }

  return payload
}

async function fetchAllAligned({ signal } = {}) {
  const records = []
  let expectedTotal = null
  let offset = 0

  for (let pageNumber = 0; pageNumber < MAX_ALIGNED_PAGES; pageNumber += 1) {
    const page = validateAlignedPage(
      await fetchJson(
        `/api/analysis/aligned?limit=${ALIGNED_PAGE_SIZE}&offset=${offset}`,
        { signal },
      ),
    )

    if (page.offset !== offset) {
      throw new MalformedResponseError(
        `The aligned API returned offset ${page.offset} when ${offset} was requested.`,
      )
    }

    if (expectedTotal === null) {
      expectedTotal = page.total
    } else if (page.total !== expectedTotal) {
      throw new MalformedResponseError(
        'The aligned API reported a different total between pages; the data changed mid-request.',
      )
    }

    records.push(...page.records)

    if (!page.hasMore) break

    if (page.count === 0) {
      throw new MalformedResponseError(
        'The aligned API reported more pages but returned no records.',
      )
    }

    offset += page.count
  }

  if (expectedTotal !== null && records.length !== expectedTotal) {
    throw new MalformedResponseError(
      `The aligned API reported ${expectedTotal} records but ${records.length} were received.`,
    )
  }

  return { total: expectedTotal ?? 0, records }
}

/**
 * Load everything the dashboard needs. The summary and report are independent
 * requests; aligned records are paged until complete.
 */
export async function loadDashboard({ signal } = {}) {
  const [summary, report, aligned] = await Promise.all([
    fetchJson('/api/analysis/summary', { signal }).then(validateSummary),
    fetchJson('/api/analysis/report', { signal }).then(validateReport),
    fetchAllAligned({ signal }),
  ])

  if (summary.metrics.pair_count !== aligned.total) {
    throw new MalformedResponseError(
      'The summary and aligned endpoints disagree on the number of valid pairs; ' +
        'the generated analysis outputs are inconsistent.',
    )
  }

  if (
    JSON.stringify(summary.additional_metrics) !==
    JSON.stringify(report.additional_metrics)
  ) {
    throw new MalformedResponseError(
      'The summary and report disagree on the additional analysis metrics.',
    )
  }

  if (summary.lead_time_hours.count !== report.lead_time_hours.count) {
    throw new MalformedResponseError(
      'The summary and report endpoints disagree on the lead-time sample count.',
    )
  }

  return {
    summary,
    report,
    aligned,
    fetchedAt: new Date().toISOString(),
  }
}
