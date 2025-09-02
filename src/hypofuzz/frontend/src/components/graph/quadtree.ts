import { DISTANCE_THRESHOLD } from "./CoverageGraph"
import { GraphLine } from "./types"

// number of pixels per sample
const QUADTREE_SAMPLE_INTERVAL = 10
// sanity check to avoid bad performance in pathological cases. ideally our sampling
// algorithm is good enough that we never hit this
const MAX_SAMPLES_PER_LINE = 1000

export interface SampledPoint {
  x: number
  y: number
  line: GraphLine
}

export function sampleLinePoints(scales: any, line: GraphLine): SampledPoint[] {
  const points: SampledPoint[] = []
  const reports = line.reports

  if (reports.length < 2) return points

  // Determine visible viewport bounds in screen space
  const viewWidth = scales.baseX.range()[1]
  const viewHeight = scales.baseY.range()[0]
  const PADDING = 0

  // Precompute viewport coordinates for all reports (avoid repeated scaling)
  const coords = reports.map((r: any) => ({
    x: scales.viewportX(scales.xValue(r)),
    y: scales.viewportY(scales.yValue(r)),
  }))

  // Build list of visible segments (any that intersect the viewport) with their screen-space lengths
  type Segment = {
    x1: number
    y1: number
    x2: number
    y2: number
    length: number
  }
  const visibleSegments: Segment[] = []
  for (let i = 1; i < coords.length; i++) {
    const { x: x1, y: y1 } = coords[i - 1]
    const { x: x2, y: y2 } = coords[i]

    // Quick reject using segment bounding box vs viewport rectangle
    const minX = Math.min(x1, x2)
    const maxX = Math.max(x1, x2)
    const minY = Math.min(y1, y2)
    const maxY = Math.max(y1, y2)
    const outside =
      maxX < -PADDING ||
      minX > viewWidth + PADDING ||
      maxY < -PADDING ||
      minY > viewHeight + PADDING
    if (outside) continue

    const length = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if (length === 0) continue
    visibleSegments.push({ x1, y1, x2, y2, length })
  }

  if (visibleSegments.length === 0) return points

  // Merge consecutive horizontal segments (cheap check: constant y within small epsilon)
  const EPS_Y = 0.0001
  const mergedSegments: Segment[] = []
  for (const seg of visibleSegments) {
    const isHoriz = Math.abs(seg.y1 - seg.y2) <= EPS_Y
    if (mergedSegments.length > 0) {
      const last = mergedSegments[mergedSegments.length - 1]
      const lastIsHoriz = Math.abs(last.y1 - last.y2) <= EPS_Y
      const sameY =
        isHoriz &&
        lastIsHoriz &&
        Math.abs((last.y1 + last.y2) / 2 - (seg.y1 + seg.y2) / 2) <= EPS_Y
      if (sameY) {
        // Extend horizontally; keep y constant
        const yConst = (last.y1 + last.y2) / 2
        const newX1 = Math.min(last.x1, seg.x1, last.x2, seg.x2)
        const newX2 = Math.max(last.x1, seg.x1, last.x2, seg.x2)
        last.x1 = newX1
        last.x2 = newX2
        last.y1 = yConst
        last.y2 = yConst
        last.length = Math.abs(newX2 - newX1)
        continue
      }
    }
    mergedSegments.push({ ...seg })
  }

  const totalVisibleLength = mergedSegments.reduce((acc, s) => acc + s.length, 0)
  if (totalVisibleLength <= 0) return points

  // Helper to dedupe closely spaced points
  function pushIfFar(x: number, y: number) {
    const last = points[points.length - 1]
    if (!last) {
      points.push({ x, y, line })
      return
    }
    const dx = x - last.x
    const dy = y - last.y
    // the farthest apart the points can be and still totally cover all hover events
    // is DISTANCE_THRESHOLD / 2.
    if (Math.sqrt(dx * dx + dy * dy) >= DISTANCE_THRESHOLD / 2) {
      points.push({ x, y, line })
    }
  }

  // 1) Always include segment endpoints for reliable hit-testing at vertices
  if (mergedSegments.length > 0) {
    pushIfFar(mergedSegments[0].x1, mergedSegments[0].y1)
    for (let i = 0; i < mergedSegments.length; i++) {
      const seg = mergedSegments[i]
      pushIfFar(seg.x2, seg.y2)
    }
  }

  // 2) Add equally spaced samples along the visible length at multiples of the interval
  const interval = QUADTREE_SAMPLE_INTERVAL
  const maxIntervals = Math.floor(totalVisibleLength / interval)
  const capacity = Math.max(0, MAX_SAMPLES_PER_LINE - points.length)
  const numIntervalSamples = Math.min(capacity, maxIntervals)

  // Sample at distances interval, 2*interval, ..., up to but not including the exact end
  for (let k = 1; k <= numIntervalSamples; k++) {
    const targetDistance = k * interval
    if (targetDistance >= totalVisibleLength) break

    let currentDistance = 0
    for (let j = 0; j < mergedSegments.length; j++) {
      const seg = mergedSegments[j]
      const nextDistance = currentDistance + seg.length
      if (targetDistance <= nextDistance || j === mergedSegments.length - 1) {
        const segT =
          seg.length > 0 ? (targetDistance - currentDistance) / seg.length : 0
        const x = seg.x1 + (seg.x2 - seg.x1) * segT
        const y = seg.y1 + (seg.y2 - seg.y1) * segT
        // Only add interval samples that are within viewport bounds
        if (x >= 0 && x <= viewWidth && y >= 0 && y <= viewHeight) {
          pushIfFar(x, y)
        }
        break
      }
      currentDistance = nextDistance
    }
  }

  return points
}
