import { useMemo, useState } from 'react'

function comparable(value) {
  const text = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text
  const normalized = text.replace(/,/g, '')
  const number = Number.parseFloat(normalized)
  return Number.isFinite(number) ? number : text.toLocaleLowerCase()
}

export function useSortableRows(rows) {
  const [sort, setSort] = useState({ column: null, direction: 'ascending' })
  const sortedRows = useMemo(() => {
    if (sort.column === null) return rows
    const sign = sort.direction === 'ascending' ? 1 : -1
    return [...rows].sort((a, b) => {
      const left = comparable(Array.isArray(a) ? a[sort.column] : a.cells[sort.column])
      const right = comparable(Array.isArray(b) ? b[sort.column] : b.cells[sort.column])
      if (left < right) return -1 * sign
      if (left > right) return sign
      return 0
    })
  }, [rows, sort])

  const toggleSort = (column) => setSort((current) => ({
    column,
    direction: current.column === column && current.direction === 'ascending' ? 'descending' : 'ascending',
  }))

  const ariaSort = (column) => sort.column === column ? sort.direction : 'none'
  return { sortedRows, toggleSort, ariaSort }
}
