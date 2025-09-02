import { ScaleContinuousNumeric } from "d3-scale"
import { line as d3_line } from "d3-shape"
import { TestStatus } from "src/types/dashboard"
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

export function DataLines({
  lines,
  viewportXScale,
  viewportYScale,
  xValue,
  yValue,
  navigate,
}: DataLinesProps) {
  // Calculate path data using D3 with viewport scales (zoom already applied)
  const lineGenerator = d3_line<GraphReport>()
    .x(d => viewportXScale(xValue(d)))
    .y(d => viewportYScale(yValue(d)))
  return (
    <g style={{ pointerEvents: "auto" }}>
      {lines.map(line => {
        const pathData = lineGenerator(line.reports) || ""

        return (
          <path
            key={`line-${line.url || "no-url"}`}
            d={pathData}
            fill="none"
            stroke={line.color}
            className={`coverage-line ${line.isActive ? "coverage-line__selected" : ""} ${
              line.status === TestStatus.FAILED ||
              line.status === TestStatus.FAILED_FATALLY
                ? "coverage-line__failing"
                : ""
            }`}
            style={{
              cursor: line.url ? "pointer" : "default",
            }}
          />
        )
      })}
    </g>
  )
}
