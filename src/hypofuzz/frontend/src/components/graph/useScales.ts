import { ScaleContinuousNumeric } from "d3-scale"
import { scaleLinear as d3_scaleLinear, scaleSymlog as d3_scaleSymlog } from "d3-scale"

import { max } from "../../utils/utils"
import { GraphReport } from "./types"

interface ZoomState {
  x: number
  y: number
  scaleX: number
}

export interface ScaleBounds {
  xMin?: number
  xMax?: number
  yMin?: number
  yMax?: number
}

const identityZoomState: ZoomState = { x: 0, y: 0, scaleX: 1 }

function getConstrainedTransform({
  zoomState,
  bounds,
  baseX,
  baseY,
}: {
  zoomState: ZoomState
  bounds: ScaleBounds
  baseX: ScaleContinuousNumeric<number, number>
  baseY: ScaleContinuousNumeric<number, number>
}) {
  if (!bounds) return zoomState

  let constrained = { ...zoomState }

  // Check horizontal bounds
  if (bounds.xMin !== undefined || bounds.xMax !== undefined) {
    const xRange = baseX.range()
    const rangeStart = xRange[0]
    const rangeEnd = xRange[1]

    const leftVisibleValue = baseX.invert(
      (rangeStart - constrained.x) / constrained.scaleX,
    )
    const rightVisibleValue = baseX.invert(
      (rangeEnd - constrained.x) / constrained.scaleX,
    )

    if (bounds.xMin !== undefined && leftVisibleValue < bounds.xMin) {
      constrained.x = rangeStart - baseX(bounds.xMin) * constrained.scaleX
    }
    if (bounds.xMax !== undefined && rightVisibleValue > bounds.xMax) {
      constrained.x = rangeEnd - baseX(bounds.xMax) * constrained.scaleX
    }
  }

  // Check vertical bounds
  if (bounds.yMin !== undefined || bounds.yMax !== undefined) {
    const yRange = baseY.range()
    const rangeTop = yRange[1]
    const rangeBottom = yRange[0]

    if (
      bounds.yMin !== undefined &&
      baseY.invert(rangeBottom - constrained.y) < bounds.yMin
    ) {
      constrained.y = rangeBottom - baseY(bounds.yMin)
    }
    if (
      bounds.yMax !== undefined &&
      baseY.invert(rangeTop - constrained.y) > bounds.yMax
    ) {
      constrained.y = rangeTop - baseY(bounds.yMax)
    }
  }

  return constrained
}

export function useScales(
  data: GraphReport[],
  scaleSetting: string,
  scaleSettingY: string,
  axisSettingX: string,
  axisSettingY: string,
  width: number,
  height: number,
  zoomState: ZoomState = identityZoomState,
  bounds: ScaleBounds,
) {
  const xValue = (report: GraphReport) =>
    axisSettingX === "time"
      ? report.linear_elapsed_time
      : report.linear_status_counts.sum()

  const yValue = (report: GraphReport) =>
    axisSettingY === "behaviors" ? report.behaviors : report.fingerprints

  const baseX = (scaleSetting === "log" ? d3_scaleSymlog() : d3_scaleLinear())
    .domain([0, max(data.map(r => xValue(r))) || 1])
    .range([0, width])

  const baseY = (scaleSettingY === "log" ? d3_scaleSymlog() : d3_scaleLinear())
    .domain([0, max(data.map(r => yValue(r))) || 0])
    .range([height, 0])

  const constrainedTransform = getConstrainedTransform({
    zoomState,
    bounds,
    baseX,
    baseY,
  })

  // Apply horizontal zoom and translation
  const originalXRange = baseX.range()
  const viewportX = baseX
    .copy()
    .range([
      originalXRange[0] * constrainedTransform.scaleX + constrainedTransform.x,
      originalXRange[1] * constrainedTransform.scaleX + constrainedTransform.x,
    ])

  // Only apply translation to Y scale, not scaling - for horizontal-only zoom
  const viewportY = baseY
    .copy()
    .range([
      baseY.range()[0] + constrainedTransform.y,
      baseY.range()[1] + constrainedTransform.y,
    ])

  return {
    xValue,
    yValue,
    baseX,
    baseY,
    viewportX,
    viewportY,
    constrainedTransform,
  }
}
