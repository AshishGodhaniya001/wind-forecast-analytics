import { useState } from 'react'
import { formatPercent, formatPower, formatSignedPower, formatTimestamp, formatWindow } from '../lib/format'
import DataQualityPanel from './DataQualityPanel'

export default function Header({ summary, report, aligned, theme, onToggleTheme, onRefresh, isRefreshing, view, onViewChange }) {
  const windowLabel = summary
    ? `${formatWindow(summary.analysis_window)} · ${summary.analysis_window.timezone}`
    : 'Analysis window loading'
  const [guideVisible, setGuideVisible] = useState(() => {
    try { return sessionStorage.getItem('wind-guide-dismissed') !== 'yes' } catch { return true }
  })

  return (
    <header className="app-header" id="summary">
      <div className="app-header__main">
        <p className="eyebrow">UK electricity utility · Forecast intelligence</p>
        <h1>Wind Forecast Analytics</h1>
        {summary ? (
          <>
            <div className="headline-row">
              <p className="headline-insight" role="status">In January 2026 the day-ahead forecast averaged {formatPower(summary.metrics.bias_mw)} ({formatPercent(summary.headline_metrics.bias_percent_of_mean_actual, 1)}) above actual generation and was above actual in {formatPercent(summary.headline_metrics.overforecast_share_percent, 1)} of hours.</p>
              <span className="verdict-badge">Good at timing, too high in level</span>
            </div>
            <details className="headline-details">
              <summary>Full accuracy headline</summary>
              <p>{summary.headline_metrics.headline_text}</p>
            </details>
            <KeyTakeaways summary={summary} />
            <p className="what-this-means"><strong>What this means:</strong> Forecasts in this month were mostly too high, so planning on the raw forecast would have overestimated wind output.</p>
            {guideVisible ? <section className="how-to-read" aria-labelledby="how-to-read-heading"><div><h2 id="how-to-read-heading">How to read this page</h2><button type="button" className="text-button" onClick={() => { setGuideVisible(false); try { sessionStorage.setItem('wind-guide-dismissed', 'yes') } catch {} }}>Dismiss for this session</button></div><ol><li>Start with the four scores: typical error, larger misses, direction, and error relative to output.</li><li>Inspect the timeline to see when forecasts tracked or missed actual generation.</li><li>Use the baseline and daily breakdowns to compare this forecast with simple alternatives.</li></ol><p className="kpi-explainer"><strong>MAE:</strong> typical miss. <strong>RMSE:</strong> larger misses count more. <strong>Bias:</strong> whether forecasts ran high or low. <strong>NMAE:</strong> error compared with average output.</p></section> : null}
          </>
        ) : null}
        <p className="lede">
          <strong>Start here:</strong> <a href="#accuracy">review scores</a> → <a href="#charts">inspect the trend</a> → <a href="#breakdowns">compare breakdowns</a>.
        </p>
        <div className="meta-row">
          <span className="chip chip--period">Analysed period: {windowLabel} · Elexon FUELHH / WINDFOR · Last updated: {report?.generated_at ? formatTimestamp(report.generated_at) : 'Loading'}</span>
        </div>
      </div>

      <div className="app-header__actions">
        <div className="header-actions__buttons">
          <button type="button" className="button" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing ? 'Reloading analysis…' : 'Reload analysis'}
          </button>
          {aligned?.records?.length ? <button type="button" className="button button--secondary" onClick={() => exportAlignedCsv(aligned.records)}>Export CSV</button> : null}
          <button type="button" className="button button--secondary theme-toggle" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} aria-pressed={theme === 'dark'} onClick={onToggleTheme}>{theme === 'dark' ? '☀' : '☾'}</button>
          {summary && report ? <DataQualityPanel summary={summary} report={report} /> : null}
          <div className="view-toggle" role="group" aria-label="Dashboard detail level"><button type="button" aria-pressed={view === 'simple'} onClick={() => onViewChange('simple')}>Simple</button><button type="button" aria-pressed={view === 'detailed'} onClick={() => onViewChange('detailed')}>Detailed</button></div>
          <details className="glossary"><summary>Glossary</summary><dl><div><dt>MAE</dt><dd>Average absolute hourly error.</dd></div><div><dt>RMSE</dt><dd>Error score that gives larger misses more weight.</dd></div><div><dt>Bias</dt><dd>Average forecast minus actual; positive means too high.</dd></div><div><dt>NMAE</dt><dd>MAE compared with average actual generation.</dd></div><div><dt>Lead time</dt><dd>How long before delivery the forecast was published.</dd></div><div><dt>Naive baseline</dt><dd>Previous day&apos;s actual generation used as a simple comparison.</dd></div><div><dt>Cutoff</dt><dd>The publication deadline used to select one forecast version.</dd></div></dl></details>
        </div>
      </div>
    </header>
  )
}

function exportAlignedCsv(records) {
  const columns = [
    ['target_start_utc', (record) => record.targetStart],
    ['actual_mw', (record) => record.actualMW],
    ['forecast_mw', (record) => record.forecastMW],
    ['error_mw', (record) => record.errorMW],
    ['lead_hours', (record) => record.leadHours],
    ['forecast_publish_time_utc', (record) => record.forecastPublishTime],
  ]
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const csv = [columns.map(([name]) => name).join(','), ...records.map((record) => columns.map(([, getValue]) => escape(getValue(record))).join(','))].join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'aligned-wind-forecast-january-2026.csv'
  link.click()
  URL.revokeObjectURL(url)
}

function KeyTakeaways({ summary }) {
  const miss = summary.additional_metrics.largest_miss
  const reduction = summary.additional_metrics.mae_reduction_vs_naive_percent
  const baseline = summary.additional_metrics.naive_previous_day_baseline
  const baselineText = reduction > 0
    ? `${formatPower(summary.metrics.mae_mw)} vs naive ${formatPower(baseline.mae_mw)} (${formatPercent(reduction, 1)} lower)`
    : `${formatPower(summary.metrics.mae_mw)} vs naive ${formatPower(baseline.mae_mw)}`

  return (
    <section className="key-takeaways" aria-labelledby="takeaways-heading">
      <h2 id="takeaways-heading">Quick read</h2>
      <ul>
        <li><strong>Bias:</strong> {formatSignedPower(summary.metrics.bias_mw)}</li>
        <li><strong>MAE vs naive:</strong> {baselineText}</li>
        <li><strong>Largest miss:</strong> {miss ? `${formatPower(miss.absolute_error_mw)} · ${formatTimestamp(miss.target_start)}` : 'Unavailable'}</li>
      </ul>
    </section>
  )
}
