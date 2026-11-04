import { formatCount, formatTimestamp } from '../lib/format'

const AUDIT_SECTIONS = [
  { key: 'missing_forecast', label: 'Missing forecasts' },
  { key: 'missing_actual', label: 'Missing actuals' },
  { key: 'conflicting_latest_publications', label: 'Conflicting latest publications' },
  { key: 'unavailable_hourly_actuals', label: 'Unavailable hourly actuals' },
]

function AuditTable({ rows }) {
  return (
    <div className="table-scroll">
      <table className="audit-table">
        <thead><tr><th scope="col">Target (UTC)</th><th scope="col">Reason</th><th scope="col">Details</th></tr></thead>
        <tbody>
          {rows.map((row, index) => {
            const details = Object.entries(row)
              .filter(([key]) => key !== 'targetStart' && key !== 'reason')
              .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
              .join('; ')
            return (
              <tr key={`${row.targetStart}-${index}`}>
                <td><time dateTime={row.targetStart}>{formatTimestamp(row.targetStart)}</time></td>
                <td>{row.reason}</td>
                <td>{details || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function DataQualityPanel({ summary, report }) {
  const { counts } = summary
  const rows = [
    { key: 'missing_forecasts', label: 'Missing forecasts', count: counts.missing_forecasts },
    { key: 'missing_actuals', label: 'Missing actuals', count: counts.missing_actuals_for_selected_forecasts },
    { key: 'conflicts', label: 'Conflicting publications', count: counts.conflicting_latest_publications },
    { key: 'unmatched', label: 'Unmatched targets', count: counts.unmatched_targets },
    { key: 'unavailable', label: 'Unavailable hourly actuals', count: counts.unavailable_hourly_actuals },
    { key: 'collapsed', label: 'Collapsed duplicate publications', count: counts.collapsed_duplicate_publications },
  ]
  const passed = rows.filter((row) => row.count === 0).length
  const auditRows = AUDIT_SECTIONS.reduce((total, section) => total + report.audit[section.key].length, 0)

  return (
    <details id="data-quality-heading" className="quality-inline">
        <summary className={passed === rows.length ? 'quality-summary--clear' : ''}>
          {passed}/{rows.length} checks passed
        </summary>
        <div className="quality-popover">
        <h2 className="sr-only">Data quality checks</h2>
        <ul className="quality-list">
          {rows.map((row) => (
            <li key={row.key}>
              <span className="quality-list__label">{row.label}</span>
              <span className={`status ${row.count === 0 ? 'status--clear' : 'status--review'}`}>
                <span aria-hidden="true">{row.count === 0 ? '✓' : '!'}</span>
                {row.count === 0 ? '0 · clear' : `${formatCount(row.count)} · review`}
              </span>
            </li>
          ))}
        </ul>
        <dl className="quality-context">
          <div><dt>Selected forecasts</dt><dd>{formatCount(counts.selected_forecasts)} of {formatCount(counts.forecast_targets)} forecast targets</dd></div>
          <div><dt>Valid aligned pairs</dt><dd>{formatCount(counts.valid_aligned_pairs)}</dd></div>
        </dl>
        <div className="audit-block">
          <h3>Audit rows</h3>
          {auditRows === 0 ? (
            <p className="note">No audit rows were recorded. Empty lists are a real result, not a loading placeholder.</p>
          ) : AUDIT_SECTIONS.filter((section) => report.audit[section.key].length > 0).map((section) => (
            <details key={section.key} className="audit-details">
              <summary>{section.label} ({formatCount(report.audit[section.key].length)})</summary>
              <AuditTable rows={report.audit[section.key]} />
            </details>
          ))}
        </div>
        </div>
    </details>
  )
}
