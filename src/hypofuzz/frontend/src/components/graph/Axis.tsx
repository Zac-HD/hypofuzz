import { ScaleContinuousNumeric, scaleLinear, scaleSymlog } from "d3-scale"

interface ZoomState {
  x: number
  y: number
  scaleX: number
}

interface AxisProps {
  // viewport scale with zoom transformations applied
  viewportScale: ScaleContinuousNumeric<number, number>
  // original scale
  baseScale: ScaleContinuousNumeric<number, number>
  orientation: "bottom" | "left"
  tickCount?: number
  transform?: string
  isLogScale?: boolean
  zoomState: ZoomState
}

interface Tick {
  offset: number
  name: string
}

function formatTick(value: number): string {
  if (value >= 1_000_000) {
    return `${Math.floor(value / 1_000_000)}M`
  } else if (value >= 1000) {
    return `${Math.floor(value / 1000)}k`
  } else if (value > 0) {
    return value.toLocaleString()
  } else {
    return "0"
  }
}

function getTicks({
  baseScale,
  viewportScale,
  tickCount,
  zoomState,
  orientation,
}: {
  baseScale: ScaleContinuousNumeric<number, number>
  viewportScale: ScaleContinuousNumeric<number, number>
  tickCount: number
  zoomState: ZoomState
  orientation: "bottom" | "left"
}): Tick[] {
  const range = baseScale.range()
  let visibleDomain: [number, number]

  if (orientation === "bottom") {
    visibleDomain = [
      baseScale.invert((range[0] - zoomState.x) / zoomState.scaleX),
      baseScale.invert((range[1] - zoomState.x) / zoomState.scaleX),
    ]
  } else {
    visibleDomain = [
      baseScale.invert(range[0] - zoomState.y),
      baseScale.invert(range[1] - zoomState.y),
    ]
  }

  let tickValues = baseScale
    .domain(visibleDomain)
    .range(range)
    .ticks(tickCount)
    // don't show negative tick values
    .filter(value => value >= 0)

  return tickValues.map(value => ({
    offset: viewportScale(value),
    name: formatTick(value),
  }))
}

export function Axis({
  baseScale,
  viewportScale,
  orientation,
  tickCount = 5,
  transform,
  zoomState,
}: AxisProps) {
  const ticks = getTicks({
    baseScale,
    viewportScale,
    tickCount,
    zoomState,
    orientation,
  })

  const isHorizontal = orientation === "bottom"
  const [x1, y1, x2, y2] = isHorizontal
    ? [0, 0, baseScale.range()[1], 0] // horizontal line
    : [0, 0, 0, baseScale.range()[0]] // vertical line

  return (
    <g className={`axis axis--${orientation}`} transform={transform}>
      {/* Main axis line */}
      <line
        className="domain"
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke="currentColor"
        strokeWidth={1}
      />

      {/* end caps */}
      <line
        className="domain"
        x1={isHorizontal ? x1 : x1}
        y1={isHorizontal ? y1 : y1}
        x2={isHorizontal ? x1 : x1 - 6}
        y2={isHorizontal ? y1 + 6 : y1}
        stroke="currentColor"
        strokeWidth={1}
      />

      <line
        className="domain"
        x1={isHorizontal ? x2 : x2}
        y1={isHorizontal ? y2 : y2}
        x2={isHorizontal ? x2 : x2 - 6}
        y2={isHorizontal ? y2 + 6 : y2}
        stroke="currentColor"
        strokeWidth={1}
      />

      {/* Tick marks and labels */}
      {ticks.map((tick, i) => {
        const tickX = isHorizontal ? tick.offset : 0
        const tickY = isHorizontal ? 0 : tick.offset
        const labelX = isHorizontal ? tick.offset : -10
        const labelY = isHorizontal ? 15 : tick.offset + 4

        return (
          <g className="tick" key={i}>
            {/* Tick mark */}
            <line
              x1={tickX}
              y1={tickY}
              x2={tickX + (isHorizontal ? 0 : -6)}
              y2={tickY + (isHorizontal ? 6 : 0)}
              stroke="currentColor"
              strokeWidth={1}
            />

            {/* Tick label */}
            <text
              x={labelX}
              y={labelY}
              textAnchor={isHorizontal ? "middle" : "end"}
              fontSize="12"
              fill="currentColor"
            >
              {tick.name}
            </text>
          </g>
        )
      })}
    </g>
  )
}
