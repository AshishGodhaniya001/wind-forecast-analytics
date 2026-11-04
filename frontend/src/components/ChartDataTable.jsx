import { useState } from 'react'
import { useSortableRows } from '../lib/tableSort'

export default function ChartDataTable({ caption, headers, rows, summary, defaultOpen = false }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const { sortedRows, toggleSort, ariaSort } = useSortableRows(rows)
  return (
    <details className="chart-data-table" open={isOpen} onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary>{isOpen ? 'Hide table' : 'Show table'} · {rows.length} rows · {summary ?? 'Chart data'}</summary>
      <div className="table-scroll">
        <table className="analysis-table">
          <caption>{caption}</caption>
          <thead>
            <tr>{headers.map((header, index) => <th scope="col" key={header} aria-sort={ariaSort(index)}><button className="table-sort" type="button" aria-label={`Sort by ${header}`} onClick={() => toggleSort(index)}>{header}<span aria-hidden="true">↕</span></button></th>)}</tr>
          </thead>
          <tbody>
            {sortedRows.length ? sortedRows.map((row, index) => (
              <tr key={index}>{row.map((value, cellIndex) => <td key={cellIndex}>{value}</td>)}</tr>
            )) : <tr><td colSpan={headers.length}>No rows are available.</td></tr>}
          </tbody>
        </table>
      </div>
    </details>
  )
}
