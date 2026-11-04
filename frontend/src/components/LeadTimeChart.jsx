import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useState } from 'react'

import { formatCount, formatPercent } from '../lib/format'
import { CHART_COLORS } from '../lib/theme'

const BUCKET_ORDER = ['<6h', '6-12h', '12-18h', '18-24h', '24-30h', '30-36h', '36-40h', '>=40h']

const BUCKET_LABELS = {
  '<6h': 'Under 6 h',
  '6-12h': '6–12 h',
  '12-18h': '12–18 h',
  '18-24h': '18–24 h',
  '24-30h': '24-30 h',
  '30-36h': '30-36 h',
  '36-40h': '36-40 h',
  '>=40h': '40 h or more',
}

function LeadTimeTooltip({ active, payload, total }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null
  const share = total > 0 ? (row.count / total) * 100 : null

  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__title">{row.label} lead time</p>
      <dl className="chart-tooltip__rows">
        <div>
          <dt>Selected forecasts</dt>
          <dd>{formatCount(row.count)}</dd>
        </div>
        <div>
          <dt>Share of sample</dt>
          <dd>{formatPercent(share, 1)}</dd>
        </div>
      </dl>
    </div>
  )
}

export default function LeadTimeChart({ lead }) {
  const [tooltipTarget, setTooltipTarget] = useState(null)
  const allData = BUCKET_ORDER.map((key) => ({
    key,
    label: BUCKET_LABELS[key],
    count: lead.buckets[key] ?? 0,
  }))
  const data = allData
  const emptyBuckets = allData.filter((row) => row.count === 0)

  const ariaLabel =
    `Horizontal bar chart of lead-time buckets for ${formatCount(lead.count)} ` +
    `selected forecasts. ` +
    data.map((row) => `${row.label}: ${formatCount(row.count)}`).join('. ') +
    '.'

  return (
    <figure className="chart-figure chart-figure--compact">
      <div className="lead-time-chart-frame">
      <div className="chart-frame chart-frame--compact" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 52, bottom: 4, left: 4 }}
            accessibilityLayer
          >
            <CartesianGrid
              stroke={CHART_COLORS.grid}
              strokeDasharray="3 3"
              horizontal={false}
            />
            <XAxis
              type="number"
              allowDecimals={false}
              tick={{ fill: CHART_COLORS.axis, fontSize: 12 }}
              axisLine={{ stroke: CHART_COLORS.grid }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={110}
              interval={0}
              tick={{ fill: CHART_COLORS.axis, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              content={<LeadTimeTooltip total={lead.count} />}
              portal={tooltipTarget}
              position={{ x: 4, y: 4 }}
              wrapperStyle={{ pointerEvents: 'none' }}
              cursor={{ fill: 'rgba(16, 32, 46, 0.06)' }}
            />
            <Bar
              dataKey="count"
              name="Selected forecasts"
              fill={CHART_COLORS.actual}
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
            >
              <LabelList
                dataKey="count"
                position="right"
                formatter={formatCount}
                fill={CHART_COLORS.zero}
                fontSize={12}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="lead-time-tooltip-target" ref={setTooltipTarget} aria-live="polite" />
      </div>
      <figcaption className="chart-caption">
        Lead time is the interval from the selected forecast&apos;s publication
        time to the target hour.
      </figcaption>
      {emptyBuckets.length ? (
        <p className="chart-caption chart-caption--lead-empty">
          No forecasts were published in these lead-time ranges: {emptyBuckets.map((row) => row.label).join(', ')}.
        </p>
      ) : null}
    </figure>
  )
}
