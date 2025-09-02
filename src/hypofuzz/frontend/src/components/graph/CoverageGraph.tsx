import {
  faCircleDot,
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
  faUser,
  faUsers,
} from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { interpolateRgb as d3_interpolateRgb } from "d3-interpolate"
import { Quadtree, quadtree } from "d3-quadtree"
import {
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
} from "d3-scale"
import {
  interpolateViridis as d3_interpolateViridis,
  schemeCategory10 as d3_schemeCategory10,
} from "d3-scale-chromatic"
import { select as d3_select } from "d3-selection"
import { zoomIdentity as d3_zoomIdentity } from "d3-zoom"
import { Set } from "immutable"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Axis } from "src/components/graph/Axis"
import { DataLines } from "src/components/graph/DataLines"
import { GraphLine, GraphReport } from "src/components/graph/types"
import { Toggle } from "src/components/Toggle"
// import BoxSelect from "src/assets/box-select.svg?react"
import { useIsMobile } from "src/hooks/useIsMobile"
import { useSetting } from "src/hooks/useSetting"
import { Test } from "src/types/test"
import { useTooltip } from "src/utils/tooltip"
import { max, min, navigateOnClick, readableNodeid } from "src/utils/utils"

import { SampledPoint, sampleLinePoints } from "./quadtree"
import { useScales } from "./useScales"
import { useZoom } from "./useZoom"

export const DISTANCE_THRESHOLD = 24
const GRAPH_HEIGHT = 270

const d3 = {
  zoomIdentity: d3_zoomIdentity,
  select: d3_select,
  scaleLinear: d3_scaleLinear,
  scaleOrdinal: d3_scaleOrdinal,
  interpolateViridis: d3_interpolateViridis,
  interpolateRgb: d3_interpolateRgb,
  schemeCategory10: d3_schemeCategory10,
}

function graphLines(
  tests: Map<string, Test>,
  viewSetting: WorkerView,
  workers_after: number | null,
  reportsColor: (nodeid: string) => string,
): GraphLine[] {
  let lines: GraphLine[] = []

  if (viewSetting === WorkerView.TOGETHER) {
    lines = Array.from(tests.entries())
      .sortKey(([nodeid, test]) => nodeid)
      .map(([nodeid, test]) => ({
        nodeid: nodeid,
        url: `/tests/${encodeURIComponent(nodeid)}`,
        reports: graphReports(test, workers_after),
        color: reportsColor(nodeid),
        isActive: false,
        status: test.status,
      }))
  } else if (viewSetting === WorkerView.SEPARATE) {
    const timestamps: number[] = []
    for (const test of tests.values()) {
      for (const workerReports of test.reports_by_worker.values()) {
        if (workerReports.length > 0) {
          timestamps.push(workerReports[0].timestamp)
        }
      }
    }

    const minTimestamp = min(timestamps) ?? 0
    const maxTimestamp = max(timestamps) ?? 0

    function timeColor(timestamp: number) {
      if (timestamps.length <= 1) {
        return timeColorScale(0.5) // Use middle color if only one worker
      }
      const normalized = (timestamp - minTimestamp) / (maxTimestamp - minTimestamp)
      return timeColorScale(normalized)
    }

    for (const [nodeid, test] of tests.entries()) {
      for (const workerReports of test.reports_by_worker.values()) {
        if (workerReports.length > 0) {
          lines.push({
            nodeid: nodeid,
            url: `/tests/${encodeURIComponent(nodeid)}`,
            reports: workerReports.map(report =>
              GraphReport.fromReport(nodeid, report),
            ),
            color: timeColor(workerReports[0].timestamp),
            isActive: false,
            status: test.status,
          })
        }
      }
    }
  } else if (viewSetting === WorkerView.LATEST) {
    for (const [nodeid, test] of tests.entries()) {
      const recentReports = max(
        Array.from(test.reports_by_worker.values()),
        reports => reports[0].elapsed_time,
      )

      if (recentReports) {
        lines.push({
          nodeid: nodeid,
          url: `/tests/${encodeURIComponent(nodeid)}`,
          reports: recentReports.map(report => GraphReport.fromReport(nodeid, report)),
          // use the same color as the linearized view
          color: reportsColor(nodeid),
          isActive: false,
          status: test.status,
        })
      }
    }
  }

  return lines
}

// lifted from github's "blame" color scale for "time since now".
//
// including the commented-out colors makes the color a bit too extreme.
const timeColorScale = d3
  .scaleLinear<string>()
  .domain([0, 1])
  .range([
    // "rgb(255, 223, 182)",
    "rgb(255, 198, 128)",
    "rgb(240, 136, 62)",
    "rgb(219, 109, 40)",
    "rgb(189, 86, 29)",
    "rgb(155, 66, 21)",
    "rgb(118, 45, 10)",
    "rgb(90, 30, 2)",
    // "rgb(61, 19, 0)"
  ])
  .interpolate(d3.interpolateRgb)

export enum WorkerView {
  TOGETHER = "linearized",
  SEPARATE = "individual",
  LATEST = "latest",
}

interface Props {
  tests: Map<string, Test>
  filterString?: string
  workers_after?: number | null
  workerViews?: WorkerView[]
  workerViewSetting: string
}

function graphReports(test: Test, workers_after: number | null): GraphReport[] {
  // zip up linear_status_counts, linear_elapsed_time, and linear_reports.
  const linearStatusCounts = test.linear_status_counts(workers_after)
  const linearElapsedTime = test.linear_elapsed_time(workers_after)
  const reports: GraphReport[] = []
  for (let i = 0; i < linearStatusCounts.length; i++) {
    const report = test.linear_reports[i]
    reports.push({
      nodeid: test.nodeid,
      linear_status_counts: linearStatusCounts[i],
      linear_elapsed_time: linearElapsedTime[i],
      behaviors: report.behaviors,
      fingerprints: report.fingerprints,
    })
  }
  return reports
}

function LogLinearToggle({
  value,
  onChange,
}: {
  value: "log" | "linear"
  onChange: (value: "log" | "linear") => void
}) {
  return (
    <Toggle
      value={value}
      onChange={onChange}
      options={[
        { value: "log", content: "Log" },
        { value: "linear", content: "Linear" },
      ]}
    />
  )
}

function LabelX() {
  const [scale, setScale] = useSetting<"log" | "linear">("graph_scale_x", "log")
  const [axis, setAxis] = useSetting<"time" | "inputs">("graph_axis_x", "time")
  return (
    <div
      className="coverage-graph__label coverage-graph__label--x"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <FontAwesomeIcon
          icon={axis === "inputs" ? faHashtag : faClock}
          style={{ fontSize: "0.9rem" }}
        />
        {axis === "inputs" ? "Inputs" : "Time"}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <LogLinearToggle value={scale} onChange={setScale} />
        <Toggle
          value={axis}
          onChange={setAxis}
          options={[
            {
              value: "inputs",
              content: <FontAwesomeIcon icon={faHashtag} />,
            },
            {
              value: "time",
              content: <FontAwesomeIcon icon={faClock} />,
            },
          ]}
        />
      </div>
    </div>
  )
}

function LabelY() {
  const [scale, setScale] = useSetting<"log" | "linear">("graph_scale_y", "linear")
  const [axis, setAxis] = useSetting<"behaviors" | "fingerprints">(
    "graph_axis_y",
    "fingerprints",
  )
  return (
    <div
      className="coverage-graph__label coverage-graph__label--y"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
        zIndex: 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <LogLinearToggle value={scale} onChange={setScale} />
        <Toggle
          value={axis}
          onChange={setAxis}
          options={[
            {
              value: "behaviors",
              content: <FontAwesomeIcon icon={faCodeBranch} />,
            },
            {
              value: "fingerprints",
              content: <FontAwesomeIcon icon={faFingerprint} />,
            },
          ]}
        />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <FontAwesomeIcon
          icon={axis === "behaviors" ? faCodeBranch : faFingerprint}
          style={{ fontSize: "0.9rem" }}
        />
        {axis === "behaviors" ? "Behaviors" : "Fingerprints"}
      </div>
    </div>
  )
}

const workerToggleContent = {
  [WorkerView.TOGETHER]: {
    content: (
      <>
        <FontAwesomeIcon icon={faUser} /> Together
      </>
    ),
    mobileContent: <FontAwesomeIcon icon={faUser} />,
  },
  [WorkerView.SEPARATE]: {
    content: (
      <>
        <FontAwesomeIcon icon={faUsers} /> Separate
      </>
    ),
    mobileContent: <FontAwesomeIcon icon={faUsers} />,
  },
  [WorkerView.LATEST]: {
    content: (
      <>
        <FontAwesomeIcon icon={faCircleDot} /> Latest
      </>
    ),
    mobileContent: <FontAwesomeIcon icon={faCircleDot} />,
  },
}

const GRAPH_MARGIN = {
  top: 5,
  right: 5,
  bottom: 25,
  left: 40,
}

type HoveredState = {
  line: GraphLine
  report: GraphReport
} | null

export function GraphComponent({
  tests,
  filterString = "",
  workers_after = null,
  viewSetting,
}: {
  tests: Map<string, Test>
  filterString?: string
  workers_after?: number | null
  viewSetting: WorkerView
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const quadtreeRef = useRef<Quadtree<SampledPoint> | null>(null)
  const [scaleSettingX, setScaleSettingX] = useSetting<"log" | "linear">(
    "graph_scale_x",
    "log",
  )
  const [scaleSettingY, setScaleSettingY] = useSetting<"log" | "linear">(
    "graph_scale_y",
    "linear",
  )
  const [axisSettingX, setAxisSettingX] = useSetting<"time" | "inputs">(
    "graph_axis_x",
    "time",
  )
  const [axisSettingY, setAxisSettingY] = useSetting<"behaviors" | "fingerprints">(
    "graph_axis_y",
    "fingerprints",
  )
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const tooltip = useTooltip()
  const [containerWidth, setContainerWidth] = useState(800)
  const [hoveredState, setHoveredState] = useState<HoveredState>(null)
  const scalesRef = useRef<typeof scales | null>(null)
  const mouseDownPosRef = useRef<{ x: number; y: number } | null>(null)

  // use the unfiltered reports as the domain so colors are stable across filtering.
  const reportsColor = d3
    .scaleOrdinal(d3.schemeCategory10)
    .domain(Array.from(tests.keys()))

  // pretty sure this is a react compiler bug, because this useMemo is necessary to avoid graphLines
  // being called on every render.
  const lines = useMemo(
    () => graphLines(tests, viewSetting, workers_after, reportsColor),
    [tests, viewSetting, workers_after],
  )
  let filteredLines = lines
  if (filterString) {
    filteredLines = lines.filter(line =>
      line.url?.toLowerCase().includes(filterString.toLowerCase()),
    )
  }

  let activeLine: GraphLine | null = null
  filteredLines.forEach(line => {
    line.isActive = false
    if (
      hoveredState != null &&
      line.nodeid === hoveredState.line.nodeid &&
      (viewSetting === WorkerView.TOGETHER
        ? true
        : line.reports[0].worker_uuid === hoveredState?.line.reports[0].worker_uuid)
    ) {
      line.isActive = true
      activeLine = line
    }
  })

  useEffect(() => {
    if (containerRef.current) {
      const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
          setContainerWidth(entry.contentRect.width)
        }
      })
      resizeObserver.observe(containerRef.current)
      return () => resizeObserver.disconnect()
    }
    return undefined
  }, [])

  const graphWidth = containerWidth - GRAPH_MARGIN.left - GRAPH_MARGIN.right
  const graphHeight = GRAPH_HEIGHT - GRAPH_MARGIN.top - GRAPH_MARGIN.bottom
  const allReports = filteredLines.flatMap(line => line.reports)

  function rebuildQuadtree() {
    // for each line, we sample points from it proportional to its current display length,
    // and track them in a quadtree. This lets us find the line closest to the cursor
    // (up to some sampling error; increase QUADTREE_SAMPLE_INTERVAL to improve this).
    // Once we have the closest line, it's cheap to find the closest report on that line for
    // the actual tooltip contents.
    const sampledPoints = filteredLines.flatMap(line =>
      sampleLinePoints(scalesRef.current!, line),
    )
    quadtreeRef.current = quadtree<SampledPoint>()
      .x(d => d.x)
      .y(d => d.y)
      .addAll(sampledPoints)
  }

  const zoom = useZoom({
    minScale: 1,
    maxScale: 50,
    containerRef,
    onZoomEnd: rebuildQuadtree,
    onDragEnd: rebuildQuadtree,
  })
  const scales = useScales(
    allReports,
    scaleSettingX,
    scaleSettingY,
    axisSettingX,
    axisSettingY,
    graphWidth,
    graphHeight,
    zoom.transform,
    { yMin: 0 },
  )

  // if we don't do this, onDragEnd (but not onZoomEnd?!) refers to the `scales` from the previous
  // render, and our quadtree updates incorrectly.
  scalesRef.current = scales

  useEffect(() => {
    rebuildQuadtree()
  }, [
    filteredLines,
    scaleSettingX,
    scaleSettingY,
    axisSettingX,
    axisSettingY,
    // rebuild when screen size changes due to eg user resizes
    graphWidth,
    graphHeight,
  ])

  return (
    <div
      ref={element => {
        if (containerRef.current !== element) {
          containerRef.current = element
        }
      }}
      style={{
        position: "relative",
        width: "100%",
        height: `${GRAPH_HEIGHT}px`,
        userSelect: "none",
        cursor: activeLine ? "pointer" : "default",
      }}
      onMouseDown={event => {
        mouseDownPosRef.current = { x: event.clientX, y: event.clientY }
        zoom.onMouseDown(event)
      }}
      onDoubleClick={zoom.onDoubleClick}
      onClick={event => {
        // If the pointer moved more than a small threshold since mousedown,
        // treat as a drag and suppress navigation.
        const start = mouseDownPosRef.current
        mouseDownPosRef.current = null
        const DRAG_SUPPRESS_PX = 5
        if (
          start &&
          (Math.abs(event.clientX - start.x) > DRAG_SUPPRESS_PX ||
            Math.abs(event.clientY - start.y) > DRAG_SUPPRESS_PX)
        ) {
          return
        }

        if (activeLine && activeLine.url) {
          navigateOnClick(event as any, activeLine.url, navigate)
        }
      }}
      onMouseMove={event => {
        const rect = event.currentTarget.getBoundingClientRect()
        const mouseX = event.clientX - rect.left - GRAPH_MARGIN.left
        const mouseY = event.clientY - rect.top - GRAPH_MARGIN.top

        if (!quadtreeRef.current) return

        const closestPoint =
          quadtreeRef.current!.find(mouseX, mouseY, DISTANCE_THRESHOLD) || null

        if (closestPoint) {
          const reports = closestPoint.line.reports

          // find the closest actual report on this line. We know the closest sampled point
          // and therefore the closest line, but not the closest report on that line.
          let closestReport = reports[0]
          let minDistance = Infinity

          reports.forEach(report => {
            const reportX = scales.viewportX(scales.xValue(report))
            const reportY = scales.viewportY(scales.yValue(report))
            const distance = Math.sqrt(
              (mouseX - reportX) ** 2 + (mouseY - reportY) ** 2,
            )

            if (distance < minDistance) {
              minDistance = distance
              closestReport = report
            }
          })

          const content = (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>
                {readableNodeid(closestReport.nodeid)}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FontAwesomeIcon icon={faCodeBranch} />
                  <span>{closestReport.behaviors.toLocaleString()}</span>
                </span>
                <span>/</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FontAwesomeIcon icon={faFingerprint} />
                  <span>{closestReport.fingerprints.toLocaleString()}</span>
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FontAwesomeIcon icon={faHashtag} />
                  <span>
                    {closestReport.linear_status_counts.sum().toLocaleString()}
                  </span>
                </span>
                <span>/</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FontAwesomeIcon icon={faClock} />
                  <span>{closestReport.linear_elapsed_time.toFixed(1)}s</span>
                </span>
              </div>
            </div>
          )

          tooltip.showTooltip(content, event.clientX, event.clientY, "coverage-graph")
          setHoveredState({
            line: closestPoint.line,
            report: closestReport,
          })
        } else {
          setHoveredState(null)
          tooltip.hideTooltip("coverage-graph")
        }
      }}
      onMouseLeave={() => {
        setHoveredState(null)
        tooltip.hideTooltip("coverage-graph")
      }}
    >
      <svg
        className="coverage-graph__svg"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: `${GRAPH_HEIGHT}px`,
          pointerEvents: "none",
        }}
      >
        <defs>
          <clipPath id="clip-content">
            {/* add some padding so the stroke width doesn't get clipped, even though the center
            of the line would still be inside the clip path */}
            <rect y={-2} width={graphWidth} height={graphHeight + 4} />
          </clipPath>
        </defs>

        <g transform={`translate(${GRAPH_MARGIN.left}, ${GRAPH_MARGIN.top})`}>
          <g clipPath="url(#clip-content)">
            <DataLines
              lines={filteredLines}
              viewportXScale={scales.viewportX}
              viewportYScale={scales.viewportY}
              xValue={scales.xValue}
              yValue={scales.yValue}
              navigate={navigate}
            />
            {hoveredState && (
              <circle
                cx={scales.viewportX(scales.xValue(hoveredState.report))}
                cy={scales.viewportY(scales.yValue(hoveredState.report))}
                r={5}
                fill={hoveredState.line.color}
                stroke="#fff"
                strokeWidth={1.5}
              />
            )}
          </g>

          <Axis
            baseScale={scales.baseX}
            viewportScale={scales.viewportX}
            orientation="bottom"
            transform={`translate(0, ${scales.baseY.range()[0]})`}
            isLogScale={scaleSettingX === "log"}
            zoomState={scales.constrainedTransform}
          />

          <Axis
            baseScale={scales.baseY}
            viewportScale={scales.viewportY}
            orientation="left"
            isLogScale={scaleSettingY === "log"}
            zoomState={scales.constrainedTransform}
          />
        </g>
      </svg>
    </div>
  )
}

function ColorLegend() {
  const colors = [
    "rgb(255, 198, 128)",
    "rgb(240, 136, 62)",
    "rgb(219, 109, 40)",
    "rgb(189, 86, 29)",
    "rgb(155, 66, 21)",
    "rgb(118, 45, 10)",
    "rgb(90, 30, 2)",
  ]

  return (
    <div className="coverage-graph__color-legend">
      <span>Older</span>
      <div style={{ display: "flex", gap: "2px" }}>
        {colors.map((color, index) => (
          <div
            key={index}
            className="coverage-graph__color-legend__square"
            style={{ backgroundColor: color }}
          />
        ))}
      </div>
      <span>Newer</span>
    </div>
  )
}

export function CoverageGraph({
  tests,
  filterString = "",
  workers_after = null,
  workerViews = [WorkerView.TOGETHER, WorkerView.SEPARATE, WorkerView.LATEST],
  workerViewSetting,
}: Props) {
  let [viewSetting, setWorkerView] = useSetting<WorkerView>(
    workerViewSetting,
    WorkerView.TOGETHER,
  )

  const workers = Set(
    Array.from(tests.values()).flatMap(test =>
      Array.from(test.reports_by_worker.values()),
    ),
  )
  const disabled = workers.size == 1
  // force view setting to be the default WorkerView.TOGETHER if we're disabled, to avoid
  // confusing people that they can't switch away from the default
  if (disabled) {
    viewSetting = WorkerView.TOGETHER
  }

  return (
    <div className="card">
      <div className="card__header" style={{ marginBottom: "1rem" }}>
        Coverage
      </div>
      <div
        style={{
          display: "flex",
          justifyContent:
            viewSetting === WorkerView.SEPARATE ? "space-between" : "flex-end",
          alignItems: viewSetting === WorkerView.SEPARATE ? "center" : "default",
          marginBottom: "1rem",
        }}
      >
        {viewSetting === WorkerView.SEPARATE && <ColorLegend />}
        <span className="tooltip">
          <Toggle
            value={viewSetting}
            onChange={setWorkerView}
            options={workerViews.map(view => ({
              value: view,
              content: workerToggleContent[view].content,
              mobileContent: workerToggleContent[view].mobileContent,
            }))}
            disabled={disabled}
          />
          {disabled && (
            <span className="tooltip__text">
              Switching display mode requires multiple workers
            </span>
          )}
        </span>
      </div>
      <div className="coverage-graph__container">
        <div
          className="coverage-graph__grid"
          style={{ marginRight: "15px", flex: 1, height: "auto" }}
        >
          {/* top left */}
          <LabelY />
          {/* top right */}
          <GraphComponent
            tests={tests}
            viewSetting={viewSetting}
            workers_after={workers_after}
            filterString={filterString}
          />
          {/* bottom left */}
          <div></div>
          {/* bottom right */}
          <LabelX />
        </div>
      </div>
    </div>
  )
}
