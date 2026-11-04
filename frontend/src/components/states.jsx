import { ApiError, MalformedResponseError } from '../api/client'

export function LoadingSkeleton() {
  return (
    <div className="loading" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading the January 2026 analysis from the API…</span>

      <div className="loading__banner">
        <span className="spinner" aria-hidden="true" />
        <div>
          <p className="loading__title">Loading the analysis</p>
          <p className="loading__text">
            Reading the generated report and aligned observations from the
            backend. No values are shown until the real response arrives.
          </p>
        </div>
      </div>

      <div className="kpi-grid" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="kpi skeleton-card" key={index}>
            <span className="skeleton skeleton--label" />
            <span className="skeleton skeleton--value" />
            <span className="skeleton skeleton--hint" />
          </div>
        ))}
      </div>

      <div className="skeleton-chart" aria-hidden="true">
        <span className="skeleton skeleton--chart" />
      </div>
      <div className="skeleton-chart" aria-hidden="true">
        <span className="skeleton skeleton--chart skeleton--short" />
      </div>
    </div>
  )
}

export function ErrorState({ error, apiBaseUrl, onRetry }) {
  const isHttpError = error instanceof ApiError && error.status !== null
  const isMalformed = error instanceof MalformedResponseError

  const title = isHttpError
    ? `The analysis API returned HTTP ${error.status}`
    : isMalformed
      ? 'The analysis API response could not be used'
      : 'The analysis API could not be reached'

  return (
    <section className="error-card" role="alert" aria-labelledby="error-title">
      <div className="error-card__icon" aria-hidden="true">
        !
      </div>
      <div>
        <h2 id="error-title">{title}</h2>
        <p className="error-card__message">{error.message}</p>

        <p className="error-card__hint">
          The dashboard does not substitute sample data or zero values when a
          request fails. Fix the connection or regenerate the analysis, then
          retry.
        </p>

        <ul className="error-card__checks">
          <li>
            Backend running at <code>{apiBaseUrl || 'the same origin'}</code>
          </li>
          <li>
            <code>backend/data/processed/analysis_report_january_2026.json</code>{' '}
            and <code>aligned_analysis_january_2026.json</code> generated
          </li>
          <li>
            Frontend origin allowed by <code>CORS_ORIGINS</code>
          </li>
        </ul>

        <div className="error-card__actions">
          <button type="button" className="button" onClick={onRetry}>
            Retry request
          </button>
        </div>

        <details className="error-card__details">
          <summary>Technical detail</summary>
          <dl>
            <div>
              <dt>Error type</dt>
              <dd>{error.name}</dd>
            </div>
            {error.status ? (
              <div>
                <dt>HTTP status</dt>
                <dd>{error.status}</dd>
              </div>
            ) : null}
            {error.code ? (
              <div>
                <dt>API code</dt>
                <dd>{error.code}</dd>
              </div>
            ) : null}
          </dl>
        </details>
      </div>
    </section>
  )
}

export function EmptyState({ title, message }) {
  return (
    <div className="empty-state" role="status">
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__message">{message}</p>
    </div>
  )
}
