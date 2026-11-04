import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { formatMW, formatNumber } from '../lib/format'
import { CHART_COLORS } from '../lib/theme'

export default function ScatterPlot({ records, caption }) {
  const points = records.map((record) => ({ ...record, actualGW: record.actualMW / 1000, forecastGW: record.forecastMW / 1000 }))
  const maximum = Math.ceil(Math.max(...points.flatMap((point) => [point.actualGW, point.forecastGW])) / 2) * 2
  const ticks = Array.from({ length: maximum / 2 + 1 }, (_, index) => index * 2)
  const domain = [0, maximum]
  return (
    <figure className="chart-figure">
      <div className="chart-frame chart-frame--scatter" role="img" aria-label={`Scatter plot of ${formatNumber(records.length)} hourly forecast and actual pairs. Points on the diagonal reference line are exact matches.`}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 20, bottom: 18, left: 10 }} accessibilityLayer>
            <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" />
            <XAxis type="number" dataKey="actualGW" name="Actual" domain={domain} ticks={ticks} allowDecimals={false} tickFormatter={(value) => formatNumber(value, 0)} tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} label={{ value: 'Actual (GW)', position: 'insideBottom', offset: -10, fill: CHART_COLORS.axis, fontSize: 12 }} />
            <YAxis type="number" dataKey="forecastGW" name="Forecast" domain={domain} ticks={ticks} allowDecimals={false} tickFormatter={(value) => formatNumber(value, 0)} width={60} tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} label={{ value: 'Forecast (GW)', angle: -90, position: 'insideLeft', fill: CHART_COLORS.axis, fontSize: 12 }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: maximum, y: maximum }]} stroke={CHART_COLORS.zero} strokeDasharray="5 4" label={{ value: '45° exact match', position: 'insideTopLeft', fill: CHART_COLORS.axis, fontSize: 11 }} />
            <Tooltip formatter={(value, name) => [formatMW(value * 1000), name]} contentStyle={{ borderRadius: 8, borderColor: CHART_COLORS.grid, backgroundColor: CHART_COLORS.surface, color: CHART_COLORS.axis, fontSize: 12 }} />
            <Scatter data={points} name="Forecast" dataKey="forecastGW" fill={CHART_COLORS.forecast} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-caption">{caption}</p>
      <p className="chart-caption">The dashed diagonal marks equal forecast and actual values; points above it show overforecasting.</p>
    </figure>
  )
}
