import Panel from './Panel'

const METRIC_LABELS = {
  error: 'Error',
  mae_mw: 'MAE',
  rmse_mw: 'RMSE',
  bias_mw: 'Bias',
  nmae_percent: 'nMAE',
  mape: 'MAPE',
}

export default function MethodologyPanel({ summary, report }) {
  const cutoff = summary.cutoff_assumption

  return (
    <Panel
      id="methodology-heading"
      title="Methodology and limitations"
      subtitle="Assumptions behind the comparison"
    >
      <details className="method-details">
        <summary>Read cutoff, period labelling, and known limitations</summary>
        <div className="method-details__content">
      <div className="methodology-block">
        <h3>Forecast cutoff</h3>
        <div className="badge-row">
          <span className="badge badge--warn">{cutoff.status}</span>
          {cutoff.not_prescribed_by_challenge ? (
            <span className="badge">Not prescribed by the challenge</span>
          ) : null}
        </div>
        <blockquote className="rule-quote">{cutoff.rule}</blockquote>
        <p className="note">{cutoff.rationale}</p>
      </div>

      <div className="methodology-block">
        <h3>Period labelling</h3>
        <p>{summary.period_labelling}</p>
      </div>

      <div className="methodology-block">
        <h3>Known limitations</h3>
        <ul className="limitations-list">
          {summary.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>
        </div>
      </details>

      <div className="callout callout--warn">
        <strong>Not a financial estimate.</strong> These are forecast-accuracy
        measures. The challenge supplies no cost, price or volume data, so no
        savings, profitability or trading impact is claimed.
      </div>

      <details className="definitions">
        <summary>Metric definitions</summary>
        <dl>
          {Object.entries(report.metric_definitions).map(([key, text]) => (
            <div key={key}>
              <dt>{METRIC_LABELS[key] ?? key}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </details>
    </Panel>
  )
}
