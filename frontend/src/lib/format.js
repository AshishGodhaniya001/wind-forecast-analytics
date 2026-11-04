/** Consistent formatting for MW, percentages, counts, timestamps and hours. */

const UTC = 'UTC'

const integerFormatter = new Intl.NumberFormat('en-GB', {
  maximumFractionDigits: 0,
})

const oneDecimalFormatter = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const twoDecimalFormatter = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const timestampFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: UTC,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

const dayFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: UTC,
  day: '2-digit',
  month: 'short',
})

const calendarDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: UTC,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

const longDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: UTC,
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

export function formatNumber(value, digits = 0) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  if (digits === 0) return integerFormatter.format(value)
  if (digits === 1) return oneDecimalFormatter.format(value)
  return twoDecimalFormatter.format(value)
}

export function formatMW(value, digits = 1) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  return `${formatNumber(value, digits)} MW`
}

export function formatPower(value, digits = 2) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  return `${formatNumber(value / 1000, digits)} GW`
}

export function formatSignedMW(value, digits = 1) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${formatNumber(Math.abs(value), digits)} MW`
}

export function formatSignedPower(value, digits = 2) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${formatNumber(Math.abs(value) / 1000, digits)} GW`
}

export function formatPercent(value, digits = 2) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  return `${formatNumber(value, digits)}%`
}

export function formatCount(value) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  return integerFormatter.format(value)
}

export function formatLeadHours(value) {
  if (!isFiniteNumber(value)) return 'Unavailable'
  return `${oneDecimalFormatter.format(value)} h`
}

export function formatTimestamp(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Invalid timestamp'
  return `${timestampFormatter.format(date)} ${UTC}`
}

export function formatDay(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return dayFormatter.format(date)
}

export function formatCalendarDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return calendarDateFormatter.format(date)
}

export function formatLongDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown period'
  return longDateFormatter.format(date)
}

/** Render an analysis window such as "1–31 January 2026". */
export function formatWindow(window) {
  if (!window?.start || !window?.end) return 'Analysis window unavailable'

  const start = new Date(window.start)
  const end = new Date(window.end)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 'Analysis window unavailable'
  }

  // The window is half-open, so the last delivery hour starts one hour before
  // the end. Show the inclusive delivery date, not the exclusive boundary.
  const lastDelivery = new Date(end.getTime() - 60 * 60 * 1000)
  const sameMonth =
    start.getUTCFullYear() === lastDelivery.getUTCFullYear() &&
    start.getUTCMonth() === lastDelivery.getUTCMonth()

  if (sameMonth) {
    const month = new Intl.DateTimeFormat('en-GB', {
      timeZone: UTC,
      month: 'long',
      year: 'numeric',
    }).format(lastDelivery)
    return `${start.getUTCDate()}–${lastDelivery.getUTCDate()} ${month}`
  }

  return `${formatLongDate(window.start)} – ${formatLongDate(lastDelivery)}`
}

export function formatResolution(seconds) {
  if (!isFiniteNumber(seconds) || seconds <= 0) return 'Unavailable'
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600
    return `${hours} hour${hours === 1 ? '' : 's'}`
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60
    return `${minutes} min`
  }
  return `${seconds} s`
}
