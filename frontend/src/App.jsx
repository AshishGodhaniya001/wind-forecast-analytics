import { lazy, useCallback, useEffect, useRef, useState } from 'react'

import { getApiBaseUrl, loadDashboard } from './api/client'
import ChartBoundary from './components/ChartBoundary'
import AdditionalAnalysis from './components/AdditionalAnalysis'
import Header from './components/Header'
import KpiCards from './components/KpiCards'
import LeadTimePanel from './components/LeadTimePanel'
import MethodologyPanel from './components/MethodologyPanel'
import Panel from './components/Panel'
import ProvenancePanel from './components/ProvenancePanel'
import SectionNav from './components/SectionNav'
import { EmptyState, ErrorState, LoadingSkeleton } from './components/states'
import { formatCount, formatWindow } from './lib/format'

// Recharts is only needed once the analysis data has arrived. Keeping the chart
// modules dynamic removes it from the initial bundle; the shared chunk is
// fetched when the dashboard first renders a chart.
const ForecastActualChart = lazy(() => import('./components/ForecastActualChart'))
const ForecastErrorChart = lazy(() => import('./components/ForecastErrorChart'))

function Dashboard({ data, view }) {
  const { summary, report, aligned } = data
  const hasPairs = summary.metrics.pair_count > 0 && aligned.records.length > 0
  const windowLabel = `${formatWindow(summary.analysis_window)} (${summary.analysis_window.timezone})`

  return (
    <>
      <KpiCards summary={summary} report={report} />

      {summary.metrics.note ? (
        <div className="callout callout--warn" role="note">
          {summary.metrics.note}
        </div>
      ) : null}

      <section className="charts-section" id="charts" aria-labelledby="charts-heading">
        <div className="section-heading">
          <h2 id="charts-heading">See how forecasts compare hour by hour</h2>
          <p>
            {hasPairs
              ? `${formatCount(aligned.records.length)} hourly comparisons. Drag the handles below to zoom; hover or tap to compare actual generation, forecast, and error.`
              : 'No valid aligned observations were produced.'}
          </p>
        </div>

        <Panel
          id="actual-forecast-heading"
          title="Day-ahead forecast and actual generation"
          subtitle={`National wind generation by hour (FUELHH actuals and WINDFOR forecast) · ${windowLabel}`}
          className="chart-card"
        >
          {hasPairs ? (
            <ChartBoundary label="forecast versus actual">
              <ForecastActualChart
                records={aligned.records}
                scatterPeakCaption={summary.additional_metrics.scatter_peak_caption}
                largestMiss={summary.additional_metrics.largest_miss}
                worstDays={summary.additional_metrics.worst_days_by_mae}
              />
            </ChartBoundary>
          ) : (
            <EmptyState
              title="No aligned observations"
              message="The analysis produced zero valid pairs, so this chart cannot be drawn. Metrics remain unavailable rather than zero."
            />
          )}
        </Panel>

        <Panel
          id="error-heading"
          title="How far the forecast was from actual"
          subtitle="Forecast minus actual, in GW · positive means forecast was higher"
          className="chart-card"
        >
          {hasPairs ? (
            <ChartBoundary label="forecast error">
              <ForecastErrorChart records={aligned.records} />
            </ChartBoundary>
          ) : (
            <EmptyState
              title="No errors to plot"
              message="Without valid aligned pairs there is no forecast error to chart."
            />
          )}
        </Panel>
      </section>

      <AdditionalAnalysis summary={summary} records={aligned.records} view={view} />

      {view === 'detailed' ? <LeadTimePanel
        lead={summary.lead_time_hours}
        leadErrors={summary.additional_metrics.by_lead_time_bucket}
      /> : null}

      {view === 'detailed' ? <div className="two-column">
        <MethodologyPanel summary={summary} report={report} />
        <ProvenancePanel summary={summary} report={report} />
      </div> : null}
    </>
  )
}

export default function App() {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })
  const [attempt, setAttempt] = useState(0)
  const [view, setView] = useState(() => {
    try { return sessionStorage.getItem('wind-dashboard-view') === 'detailed' ? 'detailed' : 'simple' } catch { return 'simple' }
  })
  const [systemTheme, setSystemTheme] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  const [themeOverride, setThemeOverride] = useState(() => {
    try {
      const saved = window.localStorage.getItem('wind-forecast-theme')
      return saved === 'light' || saved === 'dark' ? saved : null
    } catch { return null }
  })
  const controllerRef = useRef(null)
  const theme = themeOverride ?? systemTheme

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = (event) => setSystemTheme(event.matches ? 'dark' : 'light')
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const toggleTheme = useCallback(() => {
    const next = theme === 'dark' ? 'light' : 'dark'
    try { window.localStorage.setItem('wind-forecast-theme', next) } catch { /* Theme still changes for this session. */ }
    setThemeOverride(next)
  }, [theme])

  useEffect(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setState({ status: 'loading', data: null, error: null })

    loadDashboard({ signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        setState({ status: 'ready', data, error: null })
      })
      .catch((error) => {
        if (controller.signal.aborted || error?.name === 'AbortError') return
        setState({ status: 'error', data: null, error })
      })

    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setAttempt((value) => value + 1)
  }, [])

  const changeView = useCallback((next) => {
    setView(next)
    try { sessionStorage.setItem('wind-dashboard-view', next) } catch { /* View still changes for this session. */ }
  }, [])

  const isRefreshing = state.status === 'loading'
  const apiBaseUrl = getApiBaseUrl()

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to dashboard
      </a>

      <div className="page">
        <Header
          summary={state.data?.summary}
          report={state.data?.report}
          aligned={state.data?.aligned}
          theme={theme}
          onToggleTheme={toggleTheme}
          onRefresh={retry}
          isRefreshing={isRefreshing}
          view={view}
          onViewChange={changeView}
        />
        <SectionNav view={view} />

        <main id="main-content" className="page__main">
          {state.status === 'loading' ? <LoadingSkeleton /> : null}
          {state.status === 'error' ? (
            <ErrorState
              error={state.error}
              apiBaseUrl={apiBaseUrl}
              onRetry={retry}
            />
          ) : null}
          {state.status === 'ready' ? <Dashboard data={state.data} view={view} /> : null}
        </main>

        <footer className="page__footer">
          <p>
            Wind Forecast Analytics · Elexon FUELHH and WINDFOR · January 2026
            (UTC)
          </p>
          <p>
            Forecast-accuracy analysis only. Not a financial, procurement or
            trading recommendation.
          </p>
        </footer>
      </div>
      <BackToTop />
    </>
  )
}

function BackToTop() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const update = () => setVisible(window.scrollY > 600)
    update()
    window.addEventListener('scroll', update, { passive: true })
    return () => window.removeEventListener('scroll', update)
  }, [])
  if (!visible) return null
  return (
    <button
      type="button"
      className="back-to-top"
      aria-label="Back to top"
      onClick={() => window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })}
    >
      ↑ <span>Back to top</span>
    </button>
  )
}
