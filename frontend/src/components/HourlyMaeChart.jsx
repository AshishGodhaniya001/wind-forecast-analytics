import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatCount, formatMW, formatNumber, formatPower, formatSignedPower } from '../lib/format'
import { CHART_COLORS } from '../lib/theme'
import ChartDataTable from './ChartDataTable'
import { niceScale } from '../lib/chartScale'

function HourTooltip({ active, payload, metric }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{row.hourLabel} UTC</p>
      <dl className="chart-tooltip__rows">
        <div><dt>{metric === 'bias' ? 'Mean bias' : 'Mean absolute error'}</dt><dd>{metric === 'bias' ? formatSignedPower(row.bias_mw) : formatMW(row.mae_mw)}</dd></div>
        <div><dt>Aligned hours</dt><dd>{formatCount(row.pair_count)}</dd></div>
      </dl>
    </div>
  )
}

export default function HourlyMaeChart({ rows, extremes, metric = 'mae' }) {
  const data = rows.map((row) => ({
    ...row,
    hourLabel: `${String(row.hour_utc).padStart(2, '0')}:00`,
    mae_gw: (row.mae_mw ?? 0) / 1000,
    bias_gw: (row.bias_mw ?? 0) / 1000,
  }))
  const plottedKey = metric === 'bias' ? 'bias_gw' : 'mae_gw'
  const plottedValues = data.map((row) => row[plottedKey])
  const axis = niceScale(metric === 'bias' ? Math.min(...plottedValues) : 0, Math.max(...plottedValues), 4, true)
  const ariaLabel = metric === 'bias'
    ? `Bar chart of mean forecast bias by UTC hour in gigawatts. Positive values mean forecast above actual; negative values mean forecast below actual.`
    : `Bar chart of mean absolute forecast error by UTC hour in gigawatts. Values range from ${formatMW(Math.min(...data.map((row) => row.mae_mw ?? 0)))} to ${formatMW(Math.max(...data.map((row) => row.mae_mw ?? 0)))}.`
  const caption = extremes?.highest_hour_utc === null
    ? 'Hourly MAE is unavailable. Under the fixed 09:20 D-1 cutoff, lead time varies with delivery hour, so hour-of-day and lead-time effects overlap.'
    : `Highest MAE: ${String(extremes.highest_hour_utc).padStart(2, '0')}:00 UTC (${formatPower(extremes.highest_mae_mw)}); lowest: ${String(extremes.lowest_hour_utc).padStart(2, '0')}:00 UTC (${formatPower(extremes.lowest_mae_mw)}). Under the fixed 09:20 D-1 cutoff, lead time varies with delivery hour, so these effects overlap.`

  return (
    <figure className="chart-figure chart-figure--compact">
      <div className="chart-frame chart-frame--compact" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 4 }} accessibilityLayer>
            <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="hourLabel" interval={2} tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} axisLine={{ stroke: CHART_COLORS.grid }} tickLine={false} />
            <YAxis domain={axis.domain} ticks={axis.ticks} allowDecimals={false} width={50} tickFormatter={(value) => formatNumber(value, 0)} tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} axisLine={false} tickLine={false} label={{ value: 'GW', angle: -90, position: 'insideLeft', fill: CHART_COLORS.axis, fontSize: 11 }} />
            <Tooltip content={<HourTooltip metric={metric} />} cursor={{ fill: 'rgba(16, 32, 46, 0.06)' }} />
            <Bar dataKey={plottedKey} name={metric === 'bias' ? 'Bias' : 'MAE'} fill={metric === 'bias' ? CHART_COLORS.forecast : CHART_COLORS.actual} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-caption">{caption}</figcaption>
      <ChartDataTable
        caption="Hourly mean absolute errors by UTC delivery hour, in GW."
        headers={['UTC hour', 'Pairs', 'MAE (GW)']}
        rows={data.map((row) => [row.hourLabel, formatCount(row.pair_count), formatPower(row.mae_mw)])}
        summary="MAE by hour"
      />
    </figure>
  )
}
