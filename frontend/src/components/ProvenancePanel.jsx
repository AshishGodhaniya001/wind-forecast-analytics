import { useState } from 'react'
import {
  formatCount,
  formatResolution,
  formatTimestamp,
} from '../lib/format'
import Panel from './Panel'

export default function ProvenancePanel({ summary, report }) {
  const [tableOpen, setTableOpen] = useState(true)
  const { sources } = report
  const { counts } = summary

  return (
    <Panel
      id="provenance-heading"
      title="Data provenance"
      subtitle="What the dashboard is comparing"
    >
      <details className="analysis-table-disclosure" open={tableOpen} onToggle={(event) => setTableOpen(event.currentTarget.open)}>
        <summary>{tableOpen ? 'Hide table' : 'Show table'} · 2 rows · Source dataset counts</summary>
      <div className="table-scroll">
        <table className="source-table">
          <caption className="sr-only">
            Elexon datasets used by the analysis
          </caption>
          <thead>
            <tr>
              <th scope="col">Dataset</th>
              <th scope="col">Role</th>
              <th scope="col">Resolution</th>
              <th scope="col">Volume</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Elexon FUELHH</strong>
                <span className="cell-note">fuel type WIND</span>
              </td>
              <td>Actual generation (FUELHH)</td>
              <td>{formatResolution(sources.actuals.resolution_seconds)}</td>
              <td>{formatCount(sources.actuals.records)} records</td>
            </tr>
            <tr>
              <td>
                <strong>Elexon WINDFOR</strong>
                <span className="cell-note">wind generation forecast</span>
              </td>
              <td>Forecast versions</td>
              <td>{formatResolution(sources.forecasts.resolution_seconds)}</td>
              <td>
                {formatCount(sources.forecasts.versions)} versions across{' '}
                {formatCount(sources.forecasts.targets)} targets
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      </details>

      <details className="provenance-details">
        <summary>How the data was selected and aligned</summary>
      <ul className="provenance-list">
        <li>
          <strong>January scoring window.</strong> The previous-day baseline for 1 January needs 48 half-hour FUELHH readings from 31 December. This brings the source total to 1,536 records, of which 1,488 are January readings. Headline metrics use January targets only (744 aligned hourly pairs).
        </li>
        <li>
          <strong>Forecast-version count.</strong> The displayed 18,080 versions across 744 January targets matches both the validated processed forecast file and the analysis report. The raw API response contains 19,272 rows before target validation; it is not the January-target count shown here.
        </li>
        <li>
          <strong>Hourly actual generation.</strong> Each hourly value is the mean of
          both 30-minute FUELHH observations; a partial hour is never averaged.
        </li>
        <li>
          <strong>Forecast versions.</strong>{' '}
          {formatCount(counts.forecast_versions_for_january_targets)} published
          versions existed for January targets. The analysis selected{' '}
          {formatCount(counts.selected_forecasts)} — one per target, published
          strictly before the cutoff. Every aligned record keeps the selected
          version&apos;s publication time.
        </li>
        <li>
          <strong>The newest forecast is not substituted.</strong> A revision
          published after the cutoff is never used, even though it exists.
        </li>
        <li>
          <strong>No live Elexon call.</strong> The API serves generated files;
          it does not query Elexon while the dashboard is open.
        </li>
      </ul>

      <p className="note">
        Source files: <code>{sources.actuals.file}</code> and{' '}
        <code>{sources.forecasts.file}</code>. Analysis generated{' '}
        <time dateTime={report.generated_at}>
          {formatTimestamp(report.generated_at)}
        </time>
        .
      </p>
      </details>
    </Panel>
  )
}
