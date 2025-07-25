import { ScaleContinuousNumeric } from "d3-scale"
import { line as d3_line } from "d3-shape"
import { useMemo, useState } from "react"
import { navigateOnClick } from "src/utils/utils"

import { GraphLine, GraphReport } from "./types"

interface DataLinesProps {
  lines: GraphLine[]
  // viewport scale with zoom applied
  viewportXScale: ScaleContinuousNumeric<number, number>
  viewportYScale: ScaleContinuousNumeric<number, number>
  xValue: (d: GraphReport) => number
  yValue: (d: GraphReport) => number
  navigate: (path: string) => void
}

interface LineData {
  pathData: string
  color: string
  url: string | null
  key: string
}

export function DataLines({
  lines,
  viewportXScale,
  viewportYScale,
  xValue,
  yValue,
  navigate,
}: DataLinesProps) {
  const [hoveredLineKey, setHoveredLineKey] = useState<string | null>(null)

  // Calculate path data using D3 with viewport scales (zoom already applied)
  const lineData = useMemo<LineData[]>(() => {
    const lineGenerator = d3_line<GraphReport>()
      .x(d => viewportXScale(xValue(d)))
      .y(d => viewportYScale(yValue(d)))

    return lines.map((line, index) => {
      const pathData = lineGenerator(line.reports) || ""

      return {
        pathData,
        color: line.color,
        url: line.url,
        key: `line-${index}-${line.url || "no-url"}`, // Stable key for React
      }
    })
  }, [lines, viewportXScale, viewportYScale, xValue, yValue])

  return (
    <g style={{ pointerEvents: "auto" }}>
      {lineData.map(line => (
        <path
          key={line.key}
          d={line.pathData}
          fill="none"
          stroke={line.color}
          className={`coverage-line ${hoveredLineKey === line.key ? "coverage-line__selected" : ""}`}
          style={{
            cursor: line.url ? "pointer" : "default",
          }}
          onMouseEnter={() => setHoveredLineKey(line.key)}
          onMouseLeave={() => setHoveredLineKey(null)}
          onClick={event => {
            if (line.url) {
              navigateOnClick(event as any, line.url, navigate)
            }
          }}
        />
      ))}
    </g>
  )
}
