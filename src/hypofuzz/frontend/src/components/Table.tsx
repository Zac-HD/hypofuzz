import { faArrowDown, faArrowUp, faTimes } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import React, { ReactNode, useMemo, useState } from "react"

import { useIsMobile } from "../hooks/useIsMobile"

interface TableHeader<T> {
  content: ReactNode
  sortKey?: (item: T) => any[] | string | number
  align?: string
}

interface TableProps<T> {
  headers: TableHeader<T>[]
  data: T[]
  row: (item: T) => React.ReactNode[]
  mobileRow?: (item: T) => React.ReactNode
  getKey?: (item: T) => string | number
  filterStrings?: (item: T) => string[]
  onFilterChange?: (filter: string) => void
}

enum SortOrder {
  ASC = 0,
  DESC = 1,
}

export function Table<T>({
  headers,
  data,
  row,
  mobileRow,
  getKey,
  onFilterChange,
  filterStrings,
}: TableProps<T>) {
  const [sortColumn, setSortColumn] = useState<number | null>(null)
  const [sortDirection, setSortDirection] = useState<SortOrder>(SortOrder.ASC)
  const [filterString, setFilterString] = useState("")
  const isMobile = useIsMobile()

  const displayData = useMemo(() => {
    let displayData = data

    if (filterString) {
      displayData = data.filter(item => {
        if (filterStrings) {
          return filterStrings(item).some(checkString =>
            checkString.toLowerCase().includes(filterString.toLowerCase()),
          )
        }
        return true
      })
    }

    if (sortColumn === null) {
      return displayData
    }

    const sorted = [...displayData].sortKey(item => headers[sortColumn].sortKey!(item))
    return sortDirection === SortOrder.ASC ? sorted : sorted.reverse()
  }, [
    data,
    sortColumn,
    sortDirection,
    headers,
    filterString,
    row,
    filterStrings,
    mobileRow,
    isMobile,
  ])

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

  function doFilterChange(filter: string) {
    setFilterString(filter)
    onFilterChange?.(filter)
  }

  return (
    <div className="table">
      {/* only show filter box if some rows are filterable */}
      {filterStrings !== undefined && (
        <div className="table__filter">
          <input
            type="text"
            placeholder="Filter"
            value={filterString}
            onChange={e => doFilterChange(e.target.value)}
            className="table__filter__input"
          />
          {filterString && (
            <span className="table__filter__clear" onClick={() => doFilterChange("")}>
              <FontAwesomeIcon icon={faTimes} />
            </span>
          )}
        </div>
      )}
      {mobileRow !== undefined && isMobile ? (
        displayData.map(item => (
          <div key={getKey ? getKey(item) : undefined}>{mobileRow(item)}</div>
        ))
      ) : (
        <table className="table__table">
          <thead>
            <tr>
              {headers.map((header, index) => (
                <th
                  key={index}
                  onClick={() => handleHeaderClick(index)}
                  className={header.sortKey ? "table--sortable" : ""}
                >
                  <div
                    className={`table__header table__header--${header.align ?? "left"}`}
                  >
                    {header.content}
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
                <tr key={getKey ? getKey(item) : undefined}>
                  {rowValue.map((cell, colIndex) => (
                    <td key={colIndex}>{cell}</td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {filterString && displayData.length < data.length && (
        <div className="table__filter-status">
          Showing {displayData.length} of {data.length} rows
          <span
            className="table__filter-status__clear"
            onClick={() => {
              setFilterString("")
              onFilterChange?.("")
            }}
          >
            [clear]
          </span>
        </div>
      )}
    </div>
  )
}
