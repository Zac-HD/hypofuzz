import React, { useEffect } from "react"
import * as d3 from "d3"
import { Observation } from "../types/dashboard"

type AxisItem = [string, (observation: Observation) => boolean]

interface MosaicChartProps {
  observations: Observation[]
  verticalAxis: AxisItem[]
  horizontalAxis: AxisItem[]
  cssStyle: (row: string, column: string) => React.CSSProperties
}

interface CellData {
  count: number
  width: number
  height: number
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

export function MosaicChart({
  observations,
  verticalAxis,
  horizontalAxis,
  cssStyle = (row, column) => ({}),
}: MosaicChartProps) {
  const matrix: CellData[][] = []
  const rowTotals: number[] = Array(verticalAxis.length).fill(0)
  const columnTotals: number[] = Array(horizontalAxis.length).fill(0)
  let grandTotal = 0

  for (let i = 0; i < verticalAxis.length; i++) {
    matrix[i] = []
    for (let j = 0; j < horizontalAxis.length; j++) {
      matrix[i][j] = { count: 0, width: 0, height: 0 }
    }
  }

  observations.forEach(observation => {
    for (let i = 0; i < verticalAxis.length; i++) {
      const [, verticalPredicate] = verticalAxis[i]

      if (verticalPredicate(observation)) {
        for (let j = 0; j < horizontalAxis.length; j++) {
          const [, horizontalPredicate] = horizontalAxis[j]

          if (horizontalPredicate(observation)) {
            matrix[i][j].count++
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

  const totalHeight = 45 * visibleRows.length

  for (let i = 0; i < verticalAxis.length; i++) {
    for (let j = 0; j < horizontalAxis.length; j++) {
      matrix[i][j].width =
        rowTotals[i] > 0 ? (matrix[i][j].count / rowTotals[i]) * 100 : 0
      matrix[i][j].height =
        columnTotals[j] > 0 ? (matrix[i][j].count / columnTotals[j]) * 100 : 0
    }
  }

  return (
    <div className="tyche__mosaic__grid">
      <div className="tyche__mosaic__column-headers">
        {visibleCols.map(colIndex => (
          <div key={colIndex} className="tyche__mosaic__column-header">
            {horizontalAxis[colIndex][0]}
          </div>
        ))}
      </div>

      {visibleRows.map(rowIndex => (
        <div key={rowIndex} className="tyche__mosaic__row">
          <div className="tyche__mosaic__row-header">{verticalAxis[rowIndex][0]}</div>

          {visibleCols.map(colIndex => (
            <div
              key={colIndex}
              className="tyche__mosaic__cell"
              style={{
                width: `${matrix[rowIndex][colIndex].width}%`,
                height: `${(matrix[rowIndex][colIndex].height / 100) * totalHeight}px`,
                ...cssStyle(verticalAxis[rowIndex][0], horizontalAxis[colIndex][0]),
              }}
              onMouseEnter={e =>
                matrix[rowIndex][colIndex].count > 0 &&
                showTooltip(
                  e,
                  `${verticalAxis[rowIndex][0]} and ${horizontalAxis[colIndex][0]}
                  <br>Count: ${matrix[rowIndex][colIndex].count}`,
                )
              }
              onMouseMove={moveTooltip}
              onMouseLeave={hideTooltip}
            >
              {matrix[rowIndex][colIndex].count > 0 && (
                <span className="tyche__mosaic__cell-value">
                  {matrix[rowIndex][colIndex].count}
                </span>
              )}
            </div>
          ))}

          <div className="tyche__mosaic__row-total">{rowTotals[rowIndex]}</div>
        </div>
      ))}

      <div className="tyche__mosaic__column-totals">
        {visibleCols.map(colIndex => (
          <div key={colIndex} className="tyche__mosaic__column-total">
            {columnTotals[colIndex]}
          </div>
        ))}
        <div className="tyche__mosaic__grand-total">{grandTotal}</div>
      </div>
    </div>
  )
}
