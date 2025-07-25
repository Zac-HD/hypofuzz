import { scaleLinear as d3_scaleLinear, scaleSymlog as d3_scaleSymlog } from "d3-scale"
import { useMemo } from "react"

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

const defaultZoomState: ZoomState = { x: 0, y: 0, scaleX: 1 }

export function useScales(
  data: GraphReport[],
  scaleSetting: string,
  scaleSettingY: string,
  axisSettingX: string,
  axisSettingY: string,
  width: number,
  height: number,
  zoomTransform: ZoomState = defaultZoomState,
  bounds?: ScaleBounds,
) {
  const accessors = useMemo(() => {
    const xValue = (report: GraphReport) =>
      axisSettingX === "time"
        ? report.linear_elapsed_time
        : report.linear_status_counts.sum()

    const yValue = (report: GraphReport) =>
      axisSettingY === "behaviors" ? report.behaviors : report.fingerprints

    return { xValue, yValue }
  }, [axisSettingX, axisSettingY])

  const baseScales = useMemo(() => {
    const xScale = (scaleSetting === "log" ? d3_scaleSymlog() : d3_scaleLinear())
      .domain([0, max(data.map(r => accessors.xValue(r))) || 1])
      .range([0, width])

    const yScale = (scaleSettingY === "log" ? d3_scaleSymlog() : d3_scaleLinear())
      .domain([0, max(data.map(r => accessors.yValue(r))) || 0])
      .range([height, 0])

    return { xScale, yScale }
  }, [data, scaleSetting, scaleSettingY, width, height, accessors])

  const constrainedTransform = useMemo(() => {
    if (!bounds) return zoomTransform

    let constrained = { ...zoomTransform }

    // Check horizontal bounds
    if (bounds.xMin !== undefined || bounds.xMax !== undefined) {
      const xRange = baseScales.xScale.range()
      const rangeStart = xRange[0]
      const rangeEnd = xRange[1]

      const leftVisibleValue = baseScales.xScale.invert(
        (rangeStart - constrained.x) / constrained.scaleX,
      )
      const rightVisibleValue = baseScales.xScale.invert(
        (rangeEnd - constrained.x) / constrained.scaleX,
      )

      if (bounds.xMin !== undefined && leftVisibleValue < bounds.xMin) {
        constrained.x = rangeStart - baseScales.xScale(bounds.xMin) * constrained.scaleX
      }
      if (bounds.xMax !== undefined && rightVisibleValue > bounds.xMax) {
        constrained.x = rangeEnd - baseScales.xScale(bounds.xMax) * constrained.scaleX
      }
    }

    // Check vertical bounds
    if (bounds.yMin !== undefined || bounds.yMax !== undefined) {
      const yRange = baseScales.yScale.range()
      const rangeTop = yRange[1]
      const rangeBottom = yRange[0]

      if (
        bounds.yMin !== undefined &&
        baseScales.yScale.invert(rangeBottom - constrained.y) < bounds.yMin
      ) {
        constrained.y = rangeBottom - baseScales.yScale(bounds.yMin)
      }
      if (
        bounds.yMax !== undefined &&
        baseScales.yScale.invert(rangeTop - constrained.y) > bounds.yMax
      ) {
        constrained.y = rangeTop - baseScales.yScale(bounds.yMax)
      }
    }

    return constrained
  }, [zoomTransform, bounds, baseScales])

  const viewportScales = useMemo(() => {
    // Apply horizontal zoom and translation
    const originalXRange = baseScales.xScale.range()
    const xScale = baseScales.xScale
      .copy()
      .range([
        originalXRange[0] * constrainedTransform.scaleX + constrainedTransform.x,
        originalXRange[1] * constrainedTransform.scaleX + constrainedTransform.x,
      ])

    // Only apply translation to Y scale, not scaling - for horizontal-only zoom
    const yScale = baseScales.yScale
      .copy()
      .range([
        baseScales.yScale.range()[0] + constrainedTransform.y,
        baseScales.yScale.range()[1] + constrainedTransform.y,
      ])

    return { xScale, yScale }
  }, [baseScales, constrainedTransform])

  return {
    ...accessors,
    baseScales,
    viewportScales,
    constrainedTransform,
  }
}
