import { useState } from 'react'
import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceDot,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  formatDay,
  formatLeadHours,
  formatMW,
  formatNumber,
  formatPower,
  formatSignedPower,
  formatSignedMW,
  formatTimestamp,
} from '../lib/format'
import { CHART_COLORS } from '../lib/theme'
import ChartDataTable from './ChartDataTable'

function range(values) {
  return values.reduce(
    (accumulator, value) => ({
      min: Math.min(accumulator.min, value),
      max: Math.max(accumulator.max, value),
    }),
    { min: Infinity, max: -Infinity },
  )
}

function ForecastTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const record = payload[0]?.payload
  if (!record) return null

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{formatTimestamp(record.targetStart)}</p>
      <dl className="chart-tooltip__rows">
        <div>
          <dt>
            <span className="line-key line-key--actual" aria-hidden="true" />
            Actual
          </dt>
          <dd>{formatMW(record.actualMW)}</dd>
        </div>
        <div>
          <dt>
            <span className="line-key line-key--forecast" aria-hidden="true" />
            Forecast
          </dt>
          <dd>{formatMW(record.forecastMW)}</dd>
        </div>
        <div>
          <dt>Error</dt>
          <dd>{formatSignedMW(record.errorMW)}</dd>
        </div>
        <div>
        <dt>Forecast version</dt>
          <dd>{formatTimestamp(record.forecastPublishTime)}</dd>
        </div>
        <div>
          <dt>Lead time</dt>
          <dd>{formatLeadHours(record.leadHours)}</dd>
        </div>
      </dl>
    </div>
  )
}

export default function ForecastActualChart({ records, scatterPeakCaption, largestMiss, worstDays = [] }) {
  const [visibleRange, setVisibleRange] = useState([0, records.length - 1])
  const plotRecords = records.map((record) => ({ ...record, actualGW: record.actualMW / 1000, forecastGW: record.forecastMW / 1000 }))
  const actual = range(records.map((record) => record.actualMW))
  const forecast = range(records.map((record) => record.forecastMW))
  const ariaLabel =
    `Line chart of actual and forecast national wind generation for ` +
    `${formatNumber(records.length)} hourly targets. Actual generation ranges ` +
    `from ${formatPower(actual.min)} to ${formatPower(actual.max)}. The selected ` +
    `forecast ranges from ${formatPower(forecast.min)} to ${formatPower(forecast.max)}. ` +
    `Actual is the solid line; forecast is the dashed line.`

  return (
    <figure className="chart-figure">
      <div className="chart-frame" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={plotRecords}
            margin={{ top: 8, right: 18, bottom: 4, left: 4 }}
            accessibilityLayer
          >
            <CartesianGrid
              stroke={CHART_COLORS.grid}
              strokeDasharray="3 3"
              vertical={false}
            />
            <XAxis
              dataKey="targetStart"
              tickFormatter={formatDay}
              minTickGap={42}
              tickMargin={8}
              tick={{ fill: CHART_COLORS.axis, fontSize: 12 }}
              axisLine={{ stroke: CHART_COLORS.grid }}
              tickLine={false}
            />
            <YAxis
              width={72}
              tickFormatter={(value) => formatNumber(value, 0)}
              tick={{ fill: CHART_COLORS.axis, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              label={{
              value: 'GW',
                angle: -90,
                position: 'insideLeft',
                fill: CHART_COLORS.axis,
                fontSize: 12,
              }}
            />
            <Tooltip
              content={<ForecastTooltip />}
              cursor={{ stroke: CHART_COLORS.grid, strokeWidth: 1 }}
            />
            {worstDays.map((day) => {
              const points = records.filter((record) => record.targetStart.startsWith(day.date_utc))
              if (!points.length) return null
              return <ReferenceArea key={day.date_utc} x1={points[0].targetStart} x2={points.at(-1).targetStart} fill={CHART_COLORS.forecast} fillOpacity={0.08} strokeOpacity={0} />
            })}
            <Legend
              verticalAlign="top"
              align="right"
              height={34}
              iconType="plainline"
              wrapperStyle={{ fontSize: 12, color: CHART_COLORS.axis }}
            />
            <Line
              type="linear"
              dataKey="actualGW"
              name="Actual (FUELHH)"
              stroke={CHART_COLORS.actual}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
            {largestMiss ? (
              <ReferenceDot x={largestMiss.target_start} y={largestMiss.forecast_mw / 1000} r={5} fill={CHART_COLORS.forecast} stroke="#ffffff" strokeWidth={2} ifOverflow="visible" />
            ) : null}
            <Brush
              dataKey="targetStart"
              height={20}
              travellerWidth={10}
              startIndex={visibleRange[0]}
              endIndex={visibleRange[1]}
              onChange={(range) => {
                if (Number.isInteger(range?.startIndex) && Number.isInteger(range?.endIndex)) {
                  setVisibleRange((current) => (
                    current[0] === range.startIndex && current[1] === range.endIndex
                      ? current
                      : [range.startIndex, range.endIndex]
                  ))
                }
              }}
              stroke={CHART_COLORS.actual}
              fill={CHART_COLORS.grid}
            />
            <Line
              type="linear"
              dataKey="forecastGW"
              name="Forecast (WINDFOR)"
              stroke={CHART_COLORS.forecast}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-controls">
        <span>Drag the handles below to zoom; hover to compare.</span>
        <button type="button" className="button button--secondary" onClick={() => setVisibleRange([0, records.length - 1])} disabled={visibleRange[0] === 0 && visibleRange[1] === records.length - 1}>Reset zoom</button>
      </div>
      <figcaption className="chart-caption">
        Timing follows actuals closely, but forecast level is higher, especially at peaks.
        Solid teal: actual generation (FUELHH). Dashed amber: the day-ahead forecast (WINDFOR)
        available at the cutoff. Use the chart with a keyboard to inspect the
        forecast version and lead time for each hour.
        Shaded bands mark the five worst days; the amber dot marks the largest miss.
      </figcaption>
      <ChartDataTable
        caption="Hourly aligned forecast and actual values, in GW."
        headers={['Target hour (UTC)', 'Actual (GW)', 'Forecast (GW)', 'Error (GW)', 'Lead time (h)']}
        rows={records.map((record) => [
          formatTimestamp(record.targetStart),
          formatPower(record.actualMW),
          formatPower(record.forecastMW),
          formatSignedPower(record.errorMW),
          formatLeadHours(record.leadHours),
        ])}
      />
    </figure>
  )
}
