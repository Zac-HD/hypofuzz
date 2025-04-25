import React, { useState, useMemo } from "react"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faArrowUp,
  faArrowDown,
  faTimes,
} from "@fortawesome/free-solid-svg-icons"

interface TableHeader<T> {
  text: string
  sortKey?: (item: T) => string | number
  filterable?: boolean
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

function textContent(node: React.ReactNode): string {
  if (typeof node === "string") {
    return node
  }
  if (React.isValidElement(node)) {
    return React.Children.toArray(node.props.children)
      .map(child => textContent(child))
      .join(" ")
  }
  return ""
}

export function Table<T>({ headers, data, row, getKey }: TableProps<T>) {
  const [sortColumn, setSortColumn] = useState<number | null>(null)
  const [sortDirection, setSortDirection] = useState<SortOrder>(SortOrder.ASC)
  const [filterString, setFilterString] = useState("")

  const displayData = useMemo(() => {
    let displayData = data

    if (filterString) {
      displayData = data.filter(item => {
        const rowValues = row(item)
        // TODO if this gets expensive, precompute/cache the fitlerable text for each row
        const filterText = headers
          .filter(header => header.filterable)
          .map(header => {
            const row = rowValues[headers.indexOf(header)]
            return textContent(row).toLowerCase()
          })
          .join(" ")
        return filterText.includes(filterString.toLowerCase())
      })
    }

    if (sortColumn === null) {
      return displayData
    }

    return [...displayData].sort((a, b) => {
      const aValue = headers[sortColumn].sortKey!(a)
      const bValue = headers[sortColumn].sortKey!(b)
      const result = aValue < bValue ? -1 : aValue > bValue ? 1 : 0
      return sortDirection === SortOrder.ASC ? result : -result
    })
  }, [data, sortColumn, sortDirection, headers, filterString, row])

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
    <div className="table">
      {/* only show filter box if some rows are filterable */}
      {headers.some(header => header.filterable) && (
        <div className="table__filter">
          <input
            type="text"
            placeholder="Filter"
            value={filterString}
            onChange={e => setFilterString(e.target.value)}
            className="table__filter__input"
          />
          {filterString && (
            <span
              className="table__filter__clear"
              onClick={() => setFilterString("")}
            >
              <FontAwesomeIcon icon={faTimes} />
            </span>
          )}
        </div>
      )}
      <table className="table__table">
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
                        <div
                          className={`table__sort__arrow table__sort__arrow--${
                            order === SortOrder.ASC ? "asc" : "desc"
                          } ${
                            sortColumn === index && sortDirection === order
                              ? "table__sort__arrow--active"
                              : ""
                          }`}
                        >
                          {order === SortOrder.ASC ? (
                            <FontAwesomeIcon icon={faArrowUp} />
                          ) : (
                            <FontAwesomeIcon icon={faArrowDown} />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayData.map(item => {
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
      {filterString && displayData.length < data.length && (
        <div className="table__filter-status">
          Showing {displayData.length} of {data.length} rows
          <span
            className="table__filter-status__clear"
            onClick={() => setFilterString("")}
          >
            [clear]
          </span>
        </div>
      )}
    </div>
  )
}
