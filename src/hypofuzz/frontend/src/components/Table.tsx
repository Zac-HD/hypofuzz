import React, { useState, useMemo } from "react"

interface TableHeader<T> {
  text: string
  sortKey?: (item: T) => string | number
}

interface TableProps<T> {
  headers: TableHeader<T>[]
  data: T[]
  row: (item: T) => React.ReactNode[]
  getKey: (item: T) => string | number
}

enum SortOrder {
  ASC = 0,
  DESC = 1,
}

export function Table<T>({ headers, data, row, getKey }: TableProps<T>) {
  const [sortColumn, setSortColumn] = useState<number | null>(null)
  const [sortDirection, setSortDirection] = useState<SortOrder>(SortOrder.ASC)

  const sortedData = useMemo(() => {
    if (sortColumn === null) {
      return data
    }

    return [...data].sort((a, b) => {
      const aValue = headers[sortColumn].sortKey!(a)
      const bValue = headers[sortColumn].sortKey!(b)
      const result = aValue < bValue ? -1 : aValue > bValue ? 1 : 0
      return sortDirection === SortOrder.ASC ? result : -result
    })
  }, [data, sortColumn, sortDirection, headers])

  const handleHeaderClick = (index: number) => {
    if (!headers[index].sortKey) return

    if (sortColumn === index) {
      setSortDirection(prev =>
        prev === SortOrder.ASC ? SortOrder.DESC : SortOrder.ASC,
      )
    } else {
      setSortColumn(index)
      setSortDirection(SortOrder.ASC)
    }
  }

  return (
    <table className="table">
      <thead>
        <tr>
          {headers.map((header, index) => (
            <th
              key={index}
              onClick={() => handleHeaderClick(index)}
              className={header.sortKey ? "table--sortable" : ""}
            >
              <div className="table__header">
                {header.text}
                {header.sortKey && (
                  <div className="table__sort">
                    {[SortOrder.ASC, SortOrder.DESC].map(order => (
                      <span
                        className={`table__sort__arrow table__sort__arrow--${
                          order === SortOrder.ASC ? "asc" : "desc"
                        } ${
                          sortColumn === index && sortDirection === order
                            ? "table__sort__arrow--active"
                            : ""
                        }`}
                      >
                        {order === SortOrder.ASC ? "↑" : "↓"}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedData.map(item => {
          const rowValue = row(item)
          console.assert(rowValue.length === headers.length)
          return (
            <tr key={getKey(item)}>
              {rowValue.map((cell, colIndex) => (
                <td key={colIndex}>{cell}</td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
