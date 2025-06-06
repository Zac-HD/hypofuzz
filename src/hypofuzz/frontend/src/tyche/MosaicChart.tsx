import React, { useEffect, useMemo } from "react"
import * as d3 from "d3"
import { Observation } from "../types/dashboard"

const MAX_MOSAIC_WIDTH = 640

type AxisItem = [string, (observation: Observation) => boolean]

interface MosaicChartProps {
  observations: Observation[]
  verticalAxis: AxisItem[]
  horizontalAxis: AxisItem[]
  cssStyle: (row: string, column: string) => React.CSSProperties
}

interface Cell {
  count: number
  widthPercent: number
}

function showTooltip(event: React.MouseEvent, value: string) {
  d3.select(".tyche-tooltip")
    .style("opacity", 1)
    .html(`${value}`)
    .style("left", `${event.pageX + 10}px`)
    .style("top", `${event.pageY - 28}px`)
}

function moveTooltip(event: React.MouseEvent) {
  d3.select(".tyche-tooltip")
    .style("left", `${event.pageX + 10}px`)
    .style("top", `${event.pageY - 28}px`)
}

function hideTooltip() {
  d3.select(".tyche-tooltip").style("opacity", 0)
}

function measureText(
  text: string,
  className: string,
): { width: number; height: number } {
  const element = document.createElement("div")
  element.className = className
  element.style.visibility = "hidden"
  element.style.position = "absolute"
  element.style.whiteSpace = "nowrap"
  element.textContent = text

  document.body.appendChild(element)
  const rect = element.getBoundingClientRect()
  document.body.removeChild(element)

  return { width: rect.width, height: rect.height }
}

export function MosaicChart({
  observations,
  verticalAxis,
  horizontalAxis,
  cssStyle = (row, column) => ({}),
}: MosaicChartProps) {
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

  observations.forEach(observation => {
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

  useEffect(() => {
    d3.select("body")
      .append("div")
      .attr("class", "tyche-tooltip")
      .style("opacity", 0)
      .style("position", "absolute")
      .style("background-color", "rgba(0, 0, 0, 0.8)")
      .style("color", "white")
      .style("border-radius", "4px")
      .style("padding", "8px")
      .style("font-size", "12px")
      .style("pointer-events", "none")
      .style("z-index", "10")

    return () => {
      d3.select(".tyche-tooltip").remove()
    }
  }, [observations])

  if (visibleRows.length === 0 || visibleCols.length === 0) {
    return <div className="tyche__mosaic__title">No observations</div>
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
            }}
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

              return (
                <div
                  key={`cell-${rowIndex}-${colIndex}`}
                  className="tyche__mosaic__cell"
                  style={{
                    width: `${cell.widthPercent}%`,
                    minWidth: `${minCellWidth}px`,
                    minHeight: `${minCellHeight}px`,
                    ...cssStyle(verticalAxis[rowIndex][0], horizontalAxis[colIndex][0]),
                  }}
                  onMouseEnter={e =>
                    showTooltip(
                      e,
                      `${verticalAxis[rowIndex][0]} and ${horizontalAxis[colIndex][0]}
                      <br>Count: ${cell.count}`,
                    )
                  }
                  onMouseMove={moveTooltip}
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
