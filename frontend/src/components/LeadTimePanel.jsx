import { lazy, useState } from 'react'

import { formatCount, formatLeadHours, formatPower, formatSignedPower } from '../lib/format'
import ChartBoundary from './ChartBoundary'
import Panel from './Panel'
import { EmptyState } from './states'

const LeadTimeChart = lazy(() => import('./LeadTimeChart'))

function LeadErrorTable({ rows }) {
  const [isOpen, setIsOpen] = useState(true)
  const populatedRows = rows.filter((row) => row.pair_count > 0)
  return (
    <details className="analysis-table-disclosure" open={isOpen} onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary>{isOpen ? 'Hide table' : 'Show table'} · {populatedRows.length} rows · MAE and bias by lead-time bucket</summary>
      <div className="table-scroll">
        <table className="analysis-table">
          <caption>Forecast error grouped by lead-time bucket</caption>
          <thead><tr><th scope="col">Lead time</th><th scope="col">Pairs</th><th scope="col">MAE</th><th scope="col">Bias</th></tr></thead>
          <tbody>{populatedRows.map((row) => <tr key={row.bucket}><td>{row.bucket}</td><td>{formatCount(row.pair_count)}</td><td>{formatPower(row.mae_mw)}</td><td>{formatSignedPower(row.bias_mw)}</td></tr>)}</tbody>
        </table>
      </div>
    </details>
  )
}

export default function LeadTimePanel({ lead, leadErrors }) {
  const hasData = lead.count > 0 && lead.buckets

  return (
    <Panel
      id="lead-time-heading"
      title="How far ahead forecasts arrived"
      subtitle="Lead time is the time between forecast publication and delivery"
    >
      {hasData ? (
        <>
          <ChartBoundary compact label="lead-time distribution">
            <LeadTimeChart lead={lead} />
          </ChartBoundary>

          <dl className="stat-grid">
            <div>
              <dt>Minimum</dt>
              <dd>{formatLeadHours(lead.min_hours)}</dd>
            </div>
            <div>
              <dt>5th percentile</dt>
              <dd>{formatLeadHours(lead.p05_hours)}</dd>
            </div>
            <div>
              <dt>Median</dt>
              <dd>{formatLeadHours(lead.median_hours)}</dd>
            </div>
            <div>
              <dt>Mean</dt>
              <dd>{formatLeadHours(lead.mean_hours)}</dd>
            </div>
            <div>
              <dt>95th percentile</dt>
              <dd>{formatLeadHours(lead.p95_hours)}</dd>
            </div>
            <div>
              <dt>Maximum</dt>
              <dd>{formatLeadHours(lead.max_hours)}</dd>
            </div>
          </dl>

          <p className="note">
            Distribution across {formatCount(lead.count)} selected forecasts. A
            longer lead time means the forecast was published further in advance
            of the delivery hour.
          </p>
          <p className="note">
            Under a fixed 09:20 cutoff on the day before delivery (D-1), lead time varies with delivery hour, so lead-time and hour-of-day effects cannot be separated.
          </p>
          <LeadErrorTable rows={leadErrors} />
        </>
      ) : (
        <EmptyState
          title="No lead-time distribution"
          message="No selected forecasts are present in the report, so lead times cannot be summarised."
        />
      )}
    </Panel>
  )
}
