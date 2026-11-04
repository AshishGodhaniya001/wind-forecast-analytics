const FALLBACK = {
  actual: '#0b6b57', forecast: '#a15c07', positive: '#b45309', negative: '#1d4ed8',
  grid: '#e3eaef', axis: '#526575', zero: '#10202e', surface: '#ffffff',
}

export const CHART_COLORS = new Proxy({}, {
  get(_target, key) {
    if (typeof document === 'undefined') return FALLBACK[key]
    return getComputedStyle(document.documentElement).getPropertyValue(`--chart-${String(key)}`).trim() || FALLBACK[key]
  },
})
