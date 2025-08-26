import { faArrowDown, faArrowUp, faTimes } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import React, { ReactNode, useEffect, useMemo, useState } from "react"
import { Pagination } from "src/components/Pagination"
import { useIsMobile } from "src/hooks/useIsMobile"

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
  getKey?: (item: T) => string | number | undefined
  filterStrings?: (item: T) => string[]
  onFilterChange?: (filter: string) => void
  perPage?: number
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
  perPage,
}: TableProps<T>) {
  const [sortColumn, setSortColumn] = useState<number | null>(null)
  const [sortDirection, setSortDirection] = useState<SortOrder>(SortOrder.ASC)
  const [filterString, setFilterString] = useState("")
  const [page, setPage] = useState(0)
  const isMobile = useIsMobile()

  function getDisplayData() {
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
  }

  // recompute display data when inputs change
  const displayData = useMemo(
    () => getDisplayData(),
    [data, filterString, sortColumn, sortDirection],
  )

  const pageCount = useMemo(() => {
    if (!perPage) {
      return 1
    }
    return Math.max(1, Math.ceil(displayData.length / perPage))
  }, [displayData.length, perPage])

  // Clamp page index if data size changes
  useEffect(() => {
    if (!perPage) {
      return
    }
    if (page >= pageCount) {
      setPage(pageCount - 1)
    }
  }, [page, pageCount, perPage])

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
    if (perPage) {
      setPage(0)
    }
  }

  function doFilterChange(filter: string) {
    setFilterString(filter)
    onFilterChange?.(filter)
    if (perPage) {
      setPage(0)
    }
  }

  const pagedData = useMemo(() => {
    if (!perPage) {
      return displayData
    }
    const start = page * perPage
    const end = (page + 1) * perPage
    return displayData.slice(start, end)
  }, [displayData, page, perPage])

  return (
    <div className="table">
      {/* only show filter box if some rows are filterable */}
      {filterStrings !== undefined && (
        <div className="table__controls">
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
          {perPage && pageCount > 1 && (
            <div className="table__pagination table__pagination--top">
              <Pagination
                currentPage={page}
                pageCount={pageCount}
                onPageChange={setPage}
              />
            </div>
          )}
        </div>
      )}
      {filterStrings === undefined && perPage && pageCount > 1 && (
        <div className="table__pagination table__pagination--top">
          <Pagination currentPage={page} pageCount={pageCount} onPageChange={setPage} />
        </div>
      )}
      {mobileRow !== undefined && isMobile ? (
        pagedData.map(item => (
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
            {pagedData.map(item => {
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
      {perPage && pageCount > 1 && (
        <div className="table__pagination table__pagination--bottom">
          <Pagination currentPage={page} pageCount={pageCount} onPageChange={setPage} />
        </div>
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
