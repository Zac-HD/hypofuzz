import "d3-transition"

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
import { quadtree } from "d3-quadtree"
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
import { max, min, readableNodeid } from "src/utils/utils"

const GRAPH_HEIGHT = 270
import { useScales } from "./useScales"
import { useZoom } from "./useZoom"

const d3 = {
  zoomIdentity: d3_zoomIdentity,
  select: d3_select,
  scaleLinear: d3_scaleLinear,
  scaleOrdinal: d3_scaleOrdinal,
  interpolateViridis: d3_interpolateViridis,
  interpolateRgb: d3_interpolateRgb,
  schemeCategory10: d3_schemeCategory10,
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
  testsLoaded: () => boolean
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
    "behaviors",
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

export function GraphComponent({
  tests,
  filterString = "",
  testsLoaded,
  workers_after = null,
  viewSetting,
}: {
  tests: Map<string, Test>
  filterString?: string
  testsLoaded: () => boolean
  workers_after?: number | null
  viewSetting: WorkerView
}) {
  const containerRef = useRef<HTMLDivElement>(null)
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
    "behaviors",
  )
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const tooltip = useTooltip()

  // use the unfiltered reports as the domain so colors are stable across filtering.
  const reportsColor = d3
    .scaleOrdinal(d3.schemeCategory10)
    .domain(Array.from(tests.keys()))

  const lines = useMemo(() => {
    let lines: GraphLine[] = []
    if (viewSetting === WorkerView.TOGETHER) {
      lines = Array.from(tests.entries())
        .sortKey(([nodeid, test]) => nodeid)
        .map(([nodeid, test]) => ({
          url: `/tests/${encodeURIComponent(nodeid)}`,
          reports: graphReports(test, workers_after),
          color: reportsColor(nodeid),
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
              url: `/tests/${encodeURIComponent(nodeid)}`,
              reports: workerReports.map(report =>
                GraphReport.fromReport(nodeid, report),
              ),
              color: timeColor(workerReports[0].timestamp),
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
            url: `/tests/${encodeURIComponent(nodeid)}`,
            reports: recentReports.map(report =>
              GraphReport.fromReport(nodeid, report),
            ),
            // use the same color as the linearized view
            color: reportsColor(nodeid),
          })
        }
      }
    }
    return lines
  }, [tests, workers_after, viewSetting, reportsColor])

  const filteredLines = useMemo(() => {
    if (!filterString) return lines
    return lines.filter(line =>
      line.url?.toLowerCase().includes(filterString.toLowerCase()),
    )
  }, [lines, filterString])

  // Get container width for dimensions calculation
  const [containerWidth, setContainerWidth] = useState(800)

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

  const dimensions = useMemo(() => {
    const margin = {
      top: 5,
      right: 5,
      bottom: 25,
      left: 40,
    }

    const width = (containerWidth || 800) - margin.left - margin.right
    const height = GRAPH_HEIGHT - margin.top - margin.bottom

    return {
      margin,
      width,
      height,
      totalWidth: width + margin.left + margin.right,
      totalHeight: height + margin.top + margin.bottom,
    }
  }, [containerWidth])

  // Flatten all reports for scale domain calculation
  const allReports = useMemo(
    () => filteredLines.flatMap(line => line.reports),
    [filteredLines],
  )

  const zoom = useZoom({ minScale: 1, maxScale: 50 })
  const scales = useScales(
    allReports,
    scaleSettingX,
    scaleSettingY,
    axisSettingX,
    axisSettingY,
    dimensions.width,
    dimensions.height,
    zoom.transform,
    { yMin: 0 },
  )

  const distanceThreshold = 10

  const graphQuadtree = useMemo(() => {
    return quadtree<GraphReport>()
      .x(d => scales.viewportScales.xScale(scales.xValue(d)))
      .y(d => scales.viewportScales.yScale(scales.yValue(d)))
      .addAll(allReports)
  }, [allReports, scales])

  const findClosestReport = useMemo(() => {
    return (chartX: number, chartY: number): GraphReport | null => {
      return graphQuadtree.find(chartX, chartY, distanceThreshold) || null
    }
  }, [graphQuadtree])

  return (
    <div
      ref={element => {
        if (containerRef.current !== element) {
          containerRef.current = element
        }
        if (zoom.containerRef.current !== element) {
          zoom.containerRef.current = element
        }
      }}
      style={{
        position: "relative",
        width: "100%",
        height: `${GRAPH_HEIGHT}px`,
        userSelect: "none",
      }}
      onMouseDown={zoom.onMouseDown}
      onDoubleClick={zoom.onDoubleClick}
      onMouseMove={event => {
        const rect = event.currentTarget.getBoundingClientRect()
        const mouseX = event.clientX - rect.left - dimensions.margin.left
        const mouseY = event.clientY - rect.top - dimensions.margin.top

        const closestReport = findClosestReport(mouseX, mouseY)

        if (closestReport) {
          const behaviors_s = closestReport.behaviors === 1 ? "" : "s"
          const fingerprints_s = closestReport.fingerprints === 1 ? "" : "s"
          const inputs_s = closestReport.linear_status_counts.sum() === 1 ? "" : "s"
          const seconds_s = closestReport.linear_elapsed_time === 1 ? "" : "s"

          const content = `
            <div style="font-weight: bold; margin-bottom: 4px;">${readableNodeid(closestReport.nodeid)}</div>
            <div>${closestReport.behaviors.toLocaleString()} behavior${behaviors_s} / ${closestReport.fingerprints.toLocaleString()} fingerprint${fingerprints_s}</div>
            <div>${closestReport.linear_status_counts.sum().toLocaleString()} input${inputs_s} / ${closestReport.linear_elapsed_time.toFixed(1)} second${seconds_s}</div>
          `

          tooltip.showTooltip(content, event.clientX, event.clientY, "coverage-graph")
        } else {
          tooltip.hideTooltip("coverage-graph")
        }
      }}
      onMouseLeave={() => {
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
            <rect y={-2} width={dimensions.width} height={dimensions.height + 4} />
          </clipPath>
        </defs>

        <g transform={`translate(${dimensions.margin.left}, ${dimensions.margin.top})`}>
          <g clipPath="url(#clip-content)">
            <DataLines
              lines={filteredLines}
              viewportXScale={scales.viewportScales.xScale}
              viewportYScale={scales.viewportScales.yScale}
              xValue={scales.xValue}
              yValue={scales.yValue}
              navigate={navigate}
            />
          </g>

          <Axis
            baseScale={scales.baseScales.xScale}
            orientation="bottom"
            transform={`translate(0, ${scales.baseScales.yScale.range()[0]})`}
            isLogScale={scaleSettingX === "log"}
            zoomTransform={scales.constrainedTransform}
          />

          <Axis
            baseScale={scales.baseScales.yScale}
            orientation="left"
            isLogScale={scaleSettingY === "log"}
            zoomTransform={scales.constrainedTransform}
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
  testsLoaded,
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
              Switching worker display mode requires multiple workers
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
            testsLoaded={testsLoaded}
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
