export function niceScale(minimum, maximum, targetIntervals = 5, includeZero = false) {
  let min = includeZero ? Math.min(0, minimum) : minimum
  let max = includeZero ? Math.max(0, maximum) : maximum
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { domain: [0, 1], ticks: [0, 1] }
  if (min === max) max = min + 1

  const rawStep = (max - min) / Math.max(targetIntervals, 1)
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const fraction = rawStep / magnitude
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  const step = niceFraction * magnitude
  const low = Math.floor(min / step) * step
  const high = Math.ceil(max / step) * step
  const count = Math.round((high - low) / step)
  const ticks = Array.from({ length: count + 1 }, (_, index) =>
    Number((low + index * step).toPrecision(12)),
  )
  return { domain: [low, high], ticks }
}
