import { lazy, Suspense, useState } from 'react'

import { formatCalendarDate, formatCount, formatPercent, formatPower, formatSignedPower, formatTimestamp } from '../lib/format'
import ChartBoundary from './ChartBoundary'
import Panel from './Panel'
import { EmptyState, LoadingSkeleton } from './states'
import { useSortableRows } from '../lib/tableSort'

const HourlyMaeChart = lazy(() => import('./HourlyMaeChart'))
const ScatterPlot = lazy(() => import('./ScatterPlot'))

function MetricTable({ caption, headers, rows, summary, openByDefault = false }) {
  const [isOpen, setIsOpen] = useState(openByDefault)
  const { sortedRows, toggleSort, ariaSort } = useSortableRows(rows)
  return (
    <details className="analysis-table-disclosure" open={isOpen} onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary>{isOpen ? 'Hide table' : 'Show table'} · {rows.length} rows · {summary ?? 'Data'}</summary>
      <div className="table-scroll">
        <table className="analysis-table">
          <caption>{caption}</caption>
          <thead>
            <tr>{headers.map((header, index) => <th scope="col" key={header} aria-sort={ariaSort(index)}><button className="table-sort" type="button" aria-label={`Sort by ${header}`} onClick={() => toggleSort(index)}>{header}<span aria-hidden="true">↕</span></button></th>)}</tr>
          </thead>
          <tbody>
            {sortedRows.length ? sortedRows.map((row) => (
              <tr key={row.key}>{row.cells.map((cell, index) => <td key={`${row.key}-${index}`}>{cell}</td>)}</tr>
            )) : <tr><td colSpan={headers.length}>No rows are available for this analysis.</td></tr>}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export default function AdditionalAnalysis({ summary, records, view = 'detailed' }) {
  const [hourlyMetric, setHourlyMetric] = useState('mae')
  const additional = summary.additional_metrics
  const metrics = summary.metrics
  const largest = additional.largest_miss
  const baselineReduction = additional.mae_reduction_vs_naive_percent
  const baselineComparison = baselineReduction > 0
    ? `${formatPercent(baselineReduction, 1)} lower`
    : baselineReduction < 0
      ? `${formatPercent(Math.abs(baselineReduction), 1)} higher`
      : 'the same'

  const modelBaselineRows = [
    {
      key: 'model',
      cells: [
        'Wind forecast',
        formatCount(metrics.pair_count),
        formatPower(metrics.mae_mw),
        formatPower(metrics.rmse_mw),
      ],
    },
    {
      key: 'naive',
      cells: [
        'Previous-day actual',
        formatCount(additional.naive_previous_day_baseline.pair_count),
        formatPower(additional.naive_previous_day_baseline.mae_mw),
        formatPower(additional.naive_previous_day_baseline.rmse_mw),
      ],
    },
  ]

  const biasHourRows = additional.by_hour_of_day.map((row) => ({
    key: String(row.hour_utc),
    cells: [
      `${String(row.hour_utc).padStart(2, '0')}:00 UTC`,
      formatCount(row.pair_count),
      formatSignedPower(row.bias_mw),
    ],
  }))

  const worstDayRows = additional.worst_days_by_mae.map((row) => ({
    key: row.date_utc,
    cells: [formatCalendarDate(`${row.date_utc}T00:00:00Z`), formatCount(row.pair_count), formatPower(row.mae_mw)],
  }))

  const sensitivityRows = additional.timestamp_sensitivity.map((row) => ({
    key: String(row.shift_hours),
    cells: [
      `${row.shift_hours > 0 ? '+' : ''}${row.shift_hours} h`,
      formatCount(row.pair_count),
      formatPower(row.mae_mw),
      formatSignedPower(row.bias_mw),
    ],
  }))

  return (
    <section className="additional-analysis" id="breakdowns" aria-label="Additional forecast analysis">
      <div className="section-heading">
        <h2>Compare forecast performance</h2>
        <p>Compare the day-ahead forecast (WINDFOR) with actual generation (FUELHH), the previous-day baseline, and the worst days.</p>
      </div>
      {view === 'detailed' ? <div className="two-column chart-diagnostics-pair">
        <Panel id="scatter-heading" title="Forecast vs actual generation" subtitle="Each point is one aligned hour; the dashed diagonal marks exact matches">
          {records?.length ? (
            <ChartBoundary label="forecast versus actual scatter plot">
              <Suspense fallback={<LoadingSkeleton />}>
                <ScatterPlot records={records} caption={additional.scatter_peak_caption} />
              </Suspense>
            </ChartBoundary>
          ) : <EmptyState title="No aligned observations" message="There are no forecast and actual pairs to plot." />}
        </Panel>
      </div> : null}
      <div className="diagnostic-grid">
        {view === 'detailed' ? <Panel id="error-distribution-heading" title="Error distribution and largest miss" subtitle="Absolute error across aligned forecast and actual hours">
          <dl className="diagnostic-stats">
            <div><dt>90th percentile of absolute error</dt><dd>{formatPower(additional.p90_absolute_error_mw)}</dd></div>
            <div><dt>95th percentile of absolute error</dt><dd>{formatPower(additional.p95_absolute_error_mw)}</dd></div>
          </dl>
          {largest ? <div className="largest-miss" role="note"><h3>Largest miss</h3><p><strong>{formatPower(largest.absolute_error_mw)}</strong> at <time dateTime={largest.target_start}>{formatTimestamp(largest.target_start)}</time>. Forecast {formatPower(largest.forecast_mw)}; actual {formatPower(largest.actual_mw)}.</p></div> : <p className="note">No aligned hours are available to identify a largest miss.</p>}
        </Panel> : null}
        <Panel
          id="naive-baseline-heading"
          title="Model versus previous day"
          subtitle="Simple baseline: use actual generation from the same hour on the previous day"
        >
          <MetricTable
            caption="Forecast model and previous-day actual baseline scores"
            headers={['Method', 'Pairs', 'MAE', 'RMSE']}
            rows={modelBaselineRows}
            summary="Model and naive baseline scores"
            openByDefault
          />
          {additional.mae_reduction_vs_naive_percent !== null ? (
            <p className="baseline-summary">
              Forecast MAE {formatPower(metrics.mae_mw)} vs naive {formatPower(additional.naive_previous_day_baseline.mae_mw)}: {baselineComparison}.
            </p>
          ) : null}
        </Panel>

        <Panel
          id="worst-days-heading"
          title="Worst days"
          subtitle="Five days with the highest mean absolute error"
        >
          <MetricTable
            caption="Five highest-error delivery days, in UTC"
            headers={['Date (UTC)', 'Pairs', 'Mean absolute error']}
            rows={worstDayRows}
            summary="Worst days by MAE"
            openByDefault
          />
        </Panel>

        {view === 'detailed' ? <Panel
          id="timestamp-sensitivity-heading"
          title="Timestamp sensitivity"
          subtitle="Recompare the actual target with a forecast shifted by one hour either way"
        >
          <MetricTable
            caption="MAE and bias under alternate forecast period labels"
            headers={['Forecast shift', 'Pairs', 'MAE', 'Bias']}
            rows={sensitivityRows}
            summary="Timestamp sensitivity scores"
            openByDefault
          />
          <p className="note">
            Results are not very sensitive to a one-hour shift: +1 h scores marginally lower MAE than 0 h. We retain 0 h as the documented period-labelling convention.
          </p>
        </Panel> : null}
      </div>

      {view === 'detailed' ? <Panel
        id="hour-error-heading"
        title="Hourly error by delivery hour"
        subtitle="UTC delivery hour; blank metrics indicate a bucket with no aligned pairs"
      >
        <div className="segmented-control" role="group" aria-label="Hourly chart metric">
          <button type="button" aria-pressed={hourlyMetric === 'mae'} onClick={() => setHourlyMetric('mae')}>MAE</button>
          <button type="button" aria-pressed={hourlyMetric === 'bias'} onClick={() => setHourlyMetric('bias')}>Bias</button>
        </div>
        {additional.by_hour_of_day.some((row) => row.pair_count > 0) ? (
          <ChartBoundary label="hourly mean absolute error">
            <Suspense fallback={<LoadingSkeleton />}>
              <HourlyMaeChart
                rows={additional.by_hour_of_day}
                extremes={additional.hour_of_day_mae_extremes}
                metric={hourlyMetric}
              />
            </Suspense>
          </ChartBoundary>
        ) : (
          <EmptyState title="No hourly data" message="There are no aligned pairs to group by UTC delivery hour." />
        )}
        <MetricTable
          caption="Forecast bias grouped by hour of day in UTC"
          headers={['Hour', 'Pairs', 'Bias']}
          rows={biasHourRows}
            summary="Bias by hour"
        />
      </Panel> : null}
    </section>
  )
}
