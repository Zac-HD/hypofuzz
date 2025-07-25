import { ScaleContinuousNumeric, scaleLinear, scaleSymlog } from "d3-scale"
import { useMemo } from "react"

interface ZoomState {
  x: number
  y: number
  scaleX: number
}

interface AxisProps {
  // original scale, not zoomed
  baseScale: ScaleContinuousNumeric<number, number>
  orientation: "bottom" | "left"
  tickCount?: number
  transform?: string
  isLogScale?: boolean
  zoomTransform?: ZoomState
}

interface TickData {
  value: number
  offset: number
  formatted: string
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

function getLogTickValues(maxValue: number): number[] {
  const tickValues = [0]
  let power = 1
  while (power <= maxValue) {
    tickValues.push(power)
    power *= 10
  }
  return tickValues
}

export function Axis({
  baseScale,
  orientation,
  tickCount = 5,
  transform,
  isLogScale = false,
  zoomTransform,
}: AxisProps) {
  const ticks = useMemo(() => {
    const baseDomain = baseScale.domain()
    const baseRange = baseScale.range()

    // Calculate visible domain based on zoom transform
    let visibleDomain: [number, number]

    if (zoomTransform) {
      const isHorizontal = orientation === "bottom"
      // only apply zoom horizontally
      const scale = isHorizontal ? zoomTransform.scaleX : 1
      const translation = isHorizontal ? zoomTransform.x : zoomTransform.y

      // Apply inverse transform to range endpoints to get visible domain
      const rangeStart = baseRange[0]
      const rangeEnd = baseRange[baseRange.length - 1]

      const visibleStart = baseScale.invert((rangeStart - translation) / scale)
      const visibleEnd = baseScale.invert((rangeEnd - translation) / scale)

      visibleDomain = [
        Math.min(visibleStart, visibleEnd),
        Math.max(visibleStart, visibleEnd),
      ]
    } else {
      visibleDomain = [baseDomain[0], baseDomain[1]]
    }

    // Generate tick values for the visible domain
    let tickValues: number[]

    if (isLogScale) {
      // For log scale, get all powers of 10 within visible range
      tickValues = getLogTickValues(visibleDomain[1]).filter(
        val => val >= visibleDomain[0] && val <= visibleDomain[1],
      )
    } else {
      // Create a temporary scale for the visible domain to generate nice ticks
      const tempScale = isLogScale ? scaleSymlog() : scaleLinear()
      tempScale.domain(visibleDomain).range(baseRange)
      tickValues = tempScale.ticks(tickCount)
    }

    // Position ticks using the base scale and apply zoom transform
    const ticks: TickData[] = tickValues.map(value => {
      const baseOffset = baseScale(value)
      let transformedOffset = baseOffset

      // Apply zoom transform to the tick position
      if (zoomTransform) {
        const isHorizontal = orientation === "bottom"
        if (isHorizontal) {
          // For horizontal axis, apply horizontal zoom transform
          transformedOffset = baseOffset * zoomTransform.scaleX + zoomTransform.x
        }
      }

      return {
        value,
        offset: transformedOffset,
        formatted: isLogScale ? formatTick(value) : value.toLocaleString(),
      }
    })

    return ticks
  }, [baseScale, tickCount, isLogScale, zoomTransform, orientation])

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
              {tick.formatted}
            </text>
          </g>
        )
      })}
    </g>
  )
}
