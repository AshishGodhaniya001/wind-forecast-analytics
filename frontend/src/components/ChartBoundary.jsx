import { Component, Suspense } from 'react'

/**
 * Suspense fallback that reserves the exact height of the chart it replaces,
 * so lazily loading the Recharts bundle does not shift the surrounding layout.
 */
export function ChartSkeleton({ compact = false, label = 'chart' }) {
  return (
    <div
      className={compact ? 'chart-frame chart-frame--compact' : 'chart-frame'}
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Loading the {label} chart…</span>
      <span className="skeleton skeleton--chart-fill" aria-hidden="true" />
    </div>
  )
}

/**
 * Catches a chart that fails to load or render. React.lazy caches a rejected
 * import promise, so a remount cannot retry it; a page reload is the honest
 * recovery path. The analysis data itself is unaffected.
 */
class ChartLoadErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="chart-load-error" role="alert">
          <p className="chart-load-error__title">
            The chart could not be displayed
          </p>
          <p className="chart-load-error__message">
            The analysis data loaded, but the chart module failed to load or
            render. No placeholder chart is shown. Reload the dashboard to try
            again.
          </p>
          <button
            type="button"
            className="button"
            onClick={() => window.location.reload()}
          >
            Retry charts
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

export default function ChartBoundary({
  children,
  compact = false,
  label = 'chart',
}) {
  return (
    <ChartLoadErrorBoundary>
      <Suspense fallback={<ChartSkeleton compact={compact} label={label} />}>
        {children}
      </Suspense>
    </ChartLoadErrorBoundary>
  )
}
