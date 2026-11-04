import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  formatDay,
  formatMW,
  formatNumber,
  formatPower,
  formatSignedMW,
  formatSignedPower,
  formatTimestamp,
} from '../lib/format'
import { CHART_COLORS } from '../lib/theme'
import ChartDataTable from './ChartDataTable'
import { niceScale } from '../lib/chartScale'

function ErrorTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const record = payload[0]?.payload
  if (!record) return null

  const direction =
    record.errorMW > 0
      ? 'Forecast above actual'
      : record.errorMW < 0
        ? 'Forecast below actual'
        : 'Forecast matched actual'

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{formatTimestamp(record.targetStart)}</p>
      <dl className="chart-tooltip__rows">
        <div>
          <dt>Error (forecast − actual)</dt>
          <dd>{formatSignedMW(record.errorMW)}</dd>
        </div>
        <div>
          <dt>Direction</dt>
          <dd>{direction}</dd>
        </div>
        <div>
          <dt>Actual</dt>
          <dd>{formatMW(record.actualMW)}</dd>
        </div>
        <div>
          <dt>Forecast</dt>
          <dd>{formatMW(record.forecastMW)}</dd>
        </div>
      </dl>
    </div>
  )
}

export default function ForecastErrorChart({ records }) {
  const errors = records.map((record) => record.errorMW)
  const min = Math.min(...errors)
  const max = Math.max(...errors)
  const plotRecords = records.map((record) => ({ ...record, errorGW: record.errorMW / 1000 }))
  const errorScale = niceScale(min / 1000, max / 1000, 6, true)
  const positiveCount = errors.filter((value) => value > 0).length
  const negativeCount = errors.filter((value) => value < 0).length

  const ariaLabel =
    `Bar chart of forecast minus actual for ${formatNumber(records.length)} ` +
    `hours. Bars above the zero line mean the forecast was higher; bars below ` +
    `mean it was lower. Error ranges from ${formatSignedPower(min)} to ` +
    `${formatSignedPower(max)}. ${formatNumber(positiveCount)} hours were positive ` +
    `and ${formatNumber(negativeCount)} were negative.`

  return (
    <figure className="chart-figure">
      <div className="chart-frame" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
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
              domain={errorScale.domain}
              ticks={errorScale.ticks}
              allowDataOverflow
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
            <ReferenceLine
              y={0}
              stroke={CHART_COLORS.zero}
              strokeWidth={1}
              label={{
                value: 'Zero error',
                position: 'insideTopRight',
                fill: CHART_COLORS.axis,
                fontSize: 11,
              }}
            />
            <Tooltip
              content={<ErrorTooltip />}
              cursor={{ fill: 'rgba(16, 32, 46, 0.06)' }}
            />
            <Bar
              dataKey="errorGW"
              name="Forecast − actual"
              maxBarSize={6}
              isAnimationActive={false}
            >
              {records.map((record) => (
                <Cell
                  key={`${record.targetStart}-${record.forecastPublishTime}`}
                  fill={
                    record.errorMW >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="chart-legend" aria-label="Error chart legend">
        <li>
          <span className="sign-key sign-key--positive" aria-hidden="true">
            +
          </span>
          Forecast above actual (bar above zero)
        </li>
        <li>
          <span className="sign-key sign-key--negative" aria-hidden="true">
            −
          </span>
          Forecast below actual (bar below zero)
        </li>
      </ul>

      <figcaption className="chart-caption">
        Each bar is one target hour. The horizontal line marks zero error, so
        the sign is readable without relying on colour.
      </figcaption>
      <ChartDataTable
        caption="Hourly forecast error values, in GW."
        headers={['Target hour (UTC)', 'Error (GW)', 'Actual (GW)', 'Forecast (GW)']}
        rows={records.map((record) => [
          formatTimestamp(record.targetStart),
          formatSignedPower(record.errorMW),
          formatPower(record.actualMW),
          formatPower(record.forecastMW),
        ])}
      />
    </figure>
  )
}
