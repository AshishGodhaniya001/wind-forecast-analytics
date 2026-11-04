import { useEffect, useRef, useState } from 'react'

import {
  formatCount,
  formatLeadHours,
  formatPower,
  formatPercent,
  formatSignedPower,
} from '../lib/format'

export default function KpiCards({ summary, report }) {
  const [openInfo, setOpenInfo] = useState(null)
  const rootRef = useRef(null)
  const { metrics, lead_time_hours: lead, analysis_window: window } = summary
  const definitions = report.metric_definitions

  useEffect(() => {
    if (!openInfo) return undefined
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpenInfo(null)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpenInfo(null)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [openInfo])

  const cards = [
    { key: 'mae', label: 'Typical hourly error', code: 'MAE', value: formatPower(metrics.mae_mw), hint: 'Average gap per hourly forecast', definition: definitions.mae_mw, info: 'The average size of the forecast error, ignoring its direction.' },
    { key: 'rmse', label: 'Larger misses', code: 'RMSE', value: formatPower(metrics.rmse_mw), hint: 'Gives larger misses more weight', definition: definitions.rmse_mw, info: 'A larger penalty for bigger errors than MAE gives.' },
    { key: 'bias', label: 'Forecast direction', code: 'Bias', value: formatSignedPower(metrics.bias_mw), hint: metrics.bias_mw > 0 ? 'Forecast ran too high' : 'Forecast ran too low', definition: definitions.bias_mw, info: 'The average signed difference between forecast and actual generation.' },
    { key: 'nmae', label: 'Error relative to output', code: 'nMAE', value: formatPercent(metrics.nmae_percent, 2), hint: 'Error compared with average actual generation', definition: definitions.nmae_percent, info: 'MAE expressed as a percentage of mean actual generation.' },
  ]

  const context = [
    { label: 'Valid pairs', value: formatCount(metrics.pair_count), definition: `of ${formatCount(window.expected_hours)} hourly targets` },
    { label: 'Mean actual', value: formatPower(metrics.mean_actual_mw) },
    { label: 'Mean forecast', value: formatPower(metrics.mean_forecast_mw) },
    { label: 'Median lead time', value: formatLeadHours(lead.median_hours) },
    { label: 'Analysis hours', value: formatCount(window.expected_hours) },
  ]

  return (
    <section className="kpi-section" id="accuracy" aria-labelledby="kpi-heading">
      <div className="section-heading">
        <h2 id="kpi-heading">Forecast accuracy</h2>
        <p>Compare the typical miss, larger misses, and whether forecasts tended to run high or low.</p>
      </div>

      <div className="kpi-grid" ref={rootRef}>
        {cards.map((card) => (
          <article className={`kpi ${openInfo === card.key ? 'kpi--info-open' : ''} ${card.key === 'bias' && metrics.bias_mw > 0 ? 'kpi--bias-positive' : ''}`} key={card.key}>
            <div className="kpi__heading">
              <p className="kpi__label">{card.label} <span className="kpi__code">{card.code}</span></p>
              <button
                className="kpi__info"
                type="button"
                title={card.info}
                aria-label={`What does ${card.label} mean?`}
                aria-describedby={`kpi-info-${card.key}`}
                aria-controls={`kpi-info-${card.key}`}
                aria-expanded={openInfo === card.key}
                onClick={() => setOpenInfo((current) => current === card.key ? null : card.key)}
              >?</button>
              <span id={`kpi-info-${card.key}`} className={`kpi__tooltip ${openInfo === card.key ? 'kpi__tooltip--open' : ''}`} role="tooltip">{card.info}</span>
            </div>
            <p
              className={`kpi__value ${card.value === 'Unavailable' ? 'kpi__value--muted' : ''}`.trim()}
            >
              {card.value}
            </p>
            <p className="kpi__hint" title={card.definition}>
              {card.hint}
            </p>
          </article>
        ))}
      </div>

      <details className="context-details">
        <summary>More context Â· {formatCount(metrics.pair_count)} valid pairs Â· {formatLeadHours(lead.median_hours)} median lead time</summary>
        <dl className="context-strip">
          {context.map((item) => (
            <div key={item.label} title={item.definition}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  )
}
