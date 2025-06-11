import { List, Set } from "immutable"
import React, { useMemo } from "react"

import { Observation } from "../types/dashboard"
import { useTooltip } from "../utils/tooltip"
import { measureText } from "../utils/utils"
import { Filter, useFilters } from "./FilterContext"

const MAX_MOSAIC_WIDTH = 640

type AxisItem = [string, (observation: Observation) => boolean]

interface MosaicChartProps {
  name: string
  observations: { raw: Observation[]; filtered: Observation[] }
  verticalAxis: AxisItem[]
  horizontalAxis: AxisItem[]
  cssStyle: (row: string, column: string) => React.CSSProperties
}

interface Cell {
  count: number
  widthPercent: number
}

export function MosaicChart({
  name,
  observations,
  verticalAxis,
  horizontalAxis,
  cssStyle = (row, column) => ({}),
}: MosaicChartProps) {
  const { filters, setFilters } = useFilters()
  const { showTooltip, hideTooltip, moveTooltip } = useTooltip()
  const mosaicFilters = filters.get(name) || []

  const selectedCells = useMemo(() => {
    if (mosaicFilters.length === 0) {
      return Set<List<number>>()
    }

    console.assert(mosaicFilters.length === 1)
    const filter = mosaicFilters[0]
    return Set(filter.extraData.selectedCells)
  }, [mosaicFilters])

  const cells: Cell[][] = []
  const rowTotals: number[] = Array(verticalAxis.length).fill(0)
  const columnTotals: number[] = Array(horizontalAxis.length).fill(0)
  let grandTotal = 0

  for (let i = 0; i < verticalAxis.length; i++) {
    cells[i] = []
    for (let j = 0; j < horizontalAxis.length; j++) {
      cells[i][j] = { count: 0, widthPercent: 0 }
    }
  }

  observations.filtered.forEach(observation => {
    for (let i = 0; i < verticalAxis.length; i++) {
      const [, verticalPredicate] = verticalAxis[i]

      if (verticalPredicate(observation)) {
        for (let j = 0; j < horizontalAxis.length; j++) {
          const [, horizontalPredicate] = horizontalAxis[j]

          if (horizontalPredicate(observation)) {
            cells[i][j].count++
            rowTotals[i]++
            columnTotals[j]++
            grandTotal++
            // An observation can only belong to one horizontal category
            break
          }
        }
        // An observation can only belong to one vertical category
        break
      }
    }
  })

  // don't show rows/columns with 0 entries
  const visibleRows = rowTotals
    .map((total, index) => (total > 0 ? index : null))
    .filter(index => index !== null)
  const visibleCols = columnTotals
    .map((total, index) => (total > 0 ? index : null))
    .filter(index => index !== null)

  const onCellClick = (rowIndex: number | null, colIndex: number | null) => {
    let newSelection = Set<List<number>>()

    if (rowIndex !== null && colIndex !== null) {
      const cell = List([rowIndex, colIndex])
      // if this cell is already selected and it's the only selection, deselect it
      if (selectedCells.equals(Set([cell]))) {
        newSelection = Set()
      } else {
        newSelection = Set([cell])
      }
    } else if (rowIndex !== null) {
      console.assert(colIndex === null)
      // select all cells in this row
      visibleCols.forEach(colIdx => {
        if (cells[rowIndex][colIdx].count > 0) {
          newSelection = newSelection.add(List([rowIndex, colIdx]))
        }
      })
    } else if (colIndex !== null) {
      console.assert(rowIndex === null)
      // select all cells in this column
      visibleRows.forEach(rowIdx => {
        if (cells[rowIdx][colIndex].count > 0) {
          newSelection = newSelection.add(List([rowIdx, colIndex]))
        }
      })
    }

    function filterName(): string {
      if (newSelection.size === 0) {
        return ""
      }

      let remainingCells = newSelection
      const canonicalNames: string[] = []

      const axes = [
        ...visibleRows.map(rowIndex => ({
          name: verticalAxis[rowIndex][0],
          cells: visibleCols
            .filter(colIndex => cells[rowIndex][colIndex].count > 0)
            .map(colIndex => List([rowIndex, colIndex])),
        })),
        ...visibleCols.map(colIndex => ({
          name: horizontalAxis[colIndex][0],
          cells: visibleRows
            .filter(rowIndex => cells[rowIndex][colIndex].count > 0)
            .map(rowIndex => List([rowIndex, colIndex])),
        })),
      ]

      for (const axis of axes) {
        if (
          axis.cells.length > 0 &&
          axis.cells.every(cell => remainingCells.has(cell))
        ) {
          canonicalNames.push(axis.name)
          remainingCells = remainingCells.subtract(Set(axis.cells))
        }
      }

      while (remainingCells.size > 0) {
        const cell = remainingCells.first()!
        const [row, col] = cell.toArray()
        canonicalNames.push(`${verticalAxis[row][0]}+${horizontalAxis[col][0]}`)
        remainingCells = remainingCells.delete(cell)
      }
      console.assert(remainingCells.size == 0)

      return canonicalNames.join(" or ")
    }

    const mosaicFilters = []
    if (newSelection.size > 0) {
      mosaicFilters.push(
        new Filter(
          filterName(),
          (obs: Observation) => {
            return newSelection.some(cell => {
              const [row, col] = cell.toArray()
              const verticalPredicate = verticalAxis[row][1]
              const horizontalPredicate = horizontalAxis[col][1]
              return verticalPredicate(obs) && horizontalPredicate(obs)
            })
          },
          name,
          { selectedCells: newSelection },
        ),
      )
    }

    const newFilters = new Map(filters)
    newFilters.set(name, mosaicFilters)
    setFilters(newFilters)
  }

  if (visibleRows.length === 0 || visibleCols.length === 0) {
    return <div>No observations</div>
  }

  const minCellWidth = 30
  const minCellHeight = 30
  const totalHeight = 45 * visibleRows.length

  for (let i = 0; i < verticalAxis.length; i++) {
    for (let j = 0; j < horizontalAxis.length; j++) {
      cells[i][j].widthPercent =
        rowTotals[i] > 0 ? (cells[i][j].count / rowTotals[i]) * 100 : 0
    }
  }

  const baseRowHeights = visibleRows.map(
    rowIndex => (rowTotals[rowIndex] / grandTotal) * totalHeight,
  )
  const rowHeights = baseRowHeights.map(height => Math.max(height, minCellHeight))

  const columnHeaderPositions = visibleCols.map((colIndex, i) => {
    if (i === 0) {
      // Left-align first column
      return 0
    } else if (i === visibleCols.length - 1) {
      // Right-align last column
      return 100
    } else {
      // Distribute middle columns evenly
      return (i / (visibleCols.length - 1)) * 100
    }
  })

  const { rowHeaderWidth, columnHeaderHeight, rowTotalWidth } = useMemo(() => {
    return {
      rowHeaderWidth: Math.max(
        ...visibleRows.map(
          rowIndex =>
            measureText(verticalAxis[rowIndex][0], "tyche__mosaic__row-header").width,
        ),
      ),
      columnHeaderHeight: Math.max(
        ...visibleCols.map(
          colIndex =>
            measureText(horizontalAxis[colIndex][0], "tyche__mosaic__column-header")
              .height,
        ),
      ),
      rowTotalWidth: Math.max(
        ...visibleRows.map(
          rowIndex =>
            measureText(rowTotals[rowIndex].toString(), "tyche__mosaic__row-total")
              .width,
        ),
      ),
    }
  }, [visibleRows, visibleCols, verticalAxis, horizontalAxis, rowTotals])

  // Enforce minimum cell widths by adjusting proportions
  const cellContainerWidth = MAX_MOSAIC_WIDTH - rowHeaderWidth - rowTotalWidth
  visibleRows.forEach(rowIndex => {
    const rowCells = visibleCols.map(colIndex => cells[rowIndex][colIndex])
    const totalRowPercent = rowCells.reduce((sum, cell) => sum + cell.widthPercent, 0)

    if (totalRowPercent > 0) {
      const actualWidths = rowCells.map(
        cell => (cell.widthPercent / 100) * cellContainerWidth,
      )

      const adjustedWidths = actualWidths.map((width, i) => {
        const cellCount = rowCells[i].count
        // only enforce minimum width on cells with data (empty cells will not be rendered)
        if (cellCount > 0 && width > 0 && width < minCellWidth) {
          return minCellWidth
        }
        return width
      })

      const totalAdjustedWidth = adjustedWidths.reduce((sum, width) => sum + width, 0)
      visibleCols.forEach((colIndex, i) => {
        cells[rowIndex][colIndex].widthPercent =
          totalAdjustedWidth > 0 ? (adjustedWidths[i] / totalAdjustedWidth) * 100 : 0
      })
    }
  })

  return (
    <div
      className="tyche__mosaic__container"
      style={{ maxWidth: `${MAX_MOSAIC_WIDTH}px` }}
    >
      <div
        className="tyche__mosaic__column-headers"
        style={{
          marginLeft: `${rowHeaderWidth}px`,
          marginRight: `${rowTotalWidth}px`,
          height: `${columnHeaderHeight}px`,
        }}
      >
        {visibleCols.map((colIndex, i) => {
          const isFirst = i === 0
          const isLast = i === visibleCols.length - 1

          return (
            <div
              key={`header-${colIndex}`}
              className="tyche__mosaic__column-header"
              style={{
                left: `${columnHeaderPositions[i]}%`,
                transform: isFirst
                  ? "translateX(0%)"
                  : isLast
                    ? "translateX(-100%)"
                    : "translateX(-50%)",
                textAlign: isFirst ? "left" : isLast ? "right" : "center",
              }}
              onClick={() => onCellClick(null, colIndex)}
            >
              {horizontalAxis[colIndex][0]}
            </div>
          )
        })}
      </div>

      {visibleRows.map((rowIndex, rowDisplayIndex) => (
        <div
          key={`row-${rowIndex}`}
          className="tyche__mosaic__row"
          style={{
            height: `${rowHeights[rowDisplayIndex]}px`,
          }}
        >
          <div
            className="tyche__mosaic__row-header"
            style={{
              width: `${rowHeaderWidth}px`,
              cursor: "pointer",
            }}
            onClick={() => onCellClick(rowIndex, null)}
          >
            {verticalAxis[rowIndex][0]}
          </div>

          <div className="tyche__mosaic__row-cells">
            {visibleCols.map(colIndex => {
              const cell = cells[rowIndex][colIndex]
              // don't display cells with no data
              if (cell.count === 0) {
                return null
              }

              const isSelected = selectedCells.has(List([rowIndex, colIndex]))
              const tooltipContent = `${verticalAxis[rowIndex][0]} and ${horizontalAxis[colIndex][0]}<br>Count: ${cell.count}`

              return (
                <div
                  key={`cell-${rowIndex}-${colIndex}`}
                  className={`tyche__mosaic__cell${isSelected ? " tyche__mosaic__cell--selected" : ""}`}
                  style={{
                    width: `${cell.widthPercent}%`,
                    minWidth: `${minCellWidth}px`,
                    minHeight: `${minCellHeight}px`,
                    ...cssStyle(verticalAxis[rowIndex][0], horizontalAxis[colIndex][0]),
                  }}
                  onClick={() => onCellClick(rowIndex, colIndex)}
                  onMouseEnter={e => showTooltip(tooltipContent, e.clientX, e.clientY)}
                  onMouseMove={e => moveTooltip(e.clientX, e.clientY)}
                  onMouseLeave={hideTooltip}
                >
                  <span className="tyche__mosaic__cell-value">{cell.count}</span>
                </div>
              )
            })}
          </div>

          <div
            className="tyche__mosaic__row-total"
            style={{
              width: `${rowTotalWidth}px`,
            }}
          >
            {rowTotals[rowIndex]}
          </div>
        </div>
      ))}

      <div
        className="tyche__mosaic__column-totals-row"
        style={{ height: `${columnHeaderHeight}px` }}
      >
        <div style={{ width: `${rowHeaderWidth}px` }}></div>
        <div
          className="tyche__mosaic__column-totals"
          style={{
            marginRight: `${rowTotalWidth}px`,
          }}
        >
          {visibleCols.map((colIndex, i) => {
            const isFirst = i === 0
            const isLast = i === visibleCols.length - 1

            return (
              <div
                key={`total-${colIndex}`}
                className="tyche__mosaic__column-total"
                style={{
                  left: `${columnHeaderPositions[i]}%`,
                  transform: isFirst
                    ? "translateX(0%)"
                    : isLast
                      ? "translateX(-100%)"
                      : "translateX(-50%)",
                  textAlign: isFirst ? "left" : isLast ? "right" : "center",
                }}
              >
                {columnTotals[colIndex]}
              </div>
            )
          })}
        </div>
        <div
          className="tyche__mosaic__grand-total"
          style={{ width: `${rowTotalWidth}px` }}
        >
          {grandTotal}
        </div>
      </div>
    </div>
  )
}
