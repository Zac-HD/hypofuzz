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
import {
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
} from "d3-scale"
import {
  interpolateViridis as d3_interpolateViridis,
  schemeCategory10 as d3_schemeCategory10,
} from "d3-scale-chromatic"
import { select as d3_select } from "d3-selection"
import {
  D3ZoomEvent,
  zoom as d3_zoom,
  zoomIdentity as d3_zoomIdentity,
  ZoomTransform,
} from "d3-zoom"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Graph, GRAPH_HEIGHT, GraphLine, GraphReport } from "src/components/graph/graph"
import { Toggle } from "src/components/Toggle"
// import BoxSelect from "src/assets/box-select.svg?react"
import { useIsMobile } from "src/hooks/useIsMobile"
import { useSetting } from "src/hooks/useSetting"
import { Test } from "src/types/test"
import { max, min } from "src/utils/utils"

const d3 = {
  zoom: d3_zoom,
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
  const svgRef = useRef<SVGSVGElement>(null)
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
  const [forceUpdate, setForceUpdate] = useState(true)
  const [zoomTransform, setZoomTransform] = useState<{
    transform: ZoomTransform | null
    zoomY: boolean
  }>({ transform: null, zoomY: false })
  const [boxSelectEnabled, setBoxSelectEnabled] = useState(false)
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [currentlyHovered, setCurrentlyHovered] = useState(false)

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
          // deterministic line color ordering, regardless of insertion order (which might vary
          // based on websocket arrival order)
          //
          // we may also want a deterministic mapping of hash(nodeid) -> color, so the color is stable
          // even across pages (overview vs individual test) or after a new test is added? But maybe we
          // *don't* want this. I'm not sure which is better ux. A graph with only one line and having
          // a non-blue color is weird.
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
              url: null,
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
            url: null,
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

  useEffect(
    () => {
      const toggleBoxSelect = () => {
        setBoxSelectEnabled(!boxSelectEnabled)
        setForceUpdate(true)
      }

      if (!svgRef.current) {
        return
      }

      // to avoid flickering of e.g. tooltips, only update the graph when
      // the cursor is not over it.
      // This is maybe a bit more aggressive than we want. We could check
      // wether a tooltip exists instead.
      //
      // Though, we should really replace all of this with updating directly
      // from websocket events, so the graph never gets redrawn. Not sure
      // yet how that would work in react.

      // also,
      // if any test is still loading from the websocket, we still want to update the graph,
      // so a user loading the page with their cursor on the graph does not see an empty
      // graph.
      if (!forceUpdate && currentlyHovered && testsLoaded()) {
        return
      }

      if (forceUpdate) {
        setForceUpdate(false)
      }

      d3.select(svgRef.current).selectAll("*").remove()
      const graph = new Graph(
        svgRef.current,
        filteredLines,
        scaleSettingX,
        scaleSettingY,
        axisSettingX,
        axisSettingY,
        navigate,
        isMobile,
      )

      if (zoomTransform.transform) {
        graph.zoom.transform(graph.chartArea, zoomTransform.transform)
      }

      graph.zoomTo(zoomTransform.transform ?? d3.zoomIdentity, zoomTransform.zoomY)

      graph.zoom.on(
        "zoom.saveTransform",
        (event: D3ZoomEvent<SVGGElement, unknown>) => {
          setZoomTransform({ transform: event.transform, zoomY: false })
        },
      )

      if (boxSelectEnabled) {
        graph.enableBoxBrush()
      }

      graph.on("boxSelectEnd", toggleBoxSelect)

      return () => {
        graph.cleanup()
      }
    },
    // TODO including zoomTransform or filteredLines makes click+drag reset badly,
    // need to figure out why
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      tests,
      scaleSettingX,
      scaleSettingY,
      axisSettingX,
      axisSettingY,
      viewSetting,
      forceUpdate,
      boxSelectEnabled,
      navigate,
      isMobile,
      currentlyHovered,
      testsLoaded,
      filterString,
      // zoomTransform,
      // filteredLines,
    ],
  )

  return (
    <svg
      className="coverage-graph__svg"
      ref={svgRef}
      style={{ width: "100%", height: `${GRAPH_HEIGHT}px` }}
      onMouseEnter={() => setCurrentlyHovered(true)}
      onMouseLeave={() => {
        setCurrentlyHovered(false)
        setForceUpdate(true)
      }}
    />
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
  const [viewSetting, setWorkerView] = useSetting<WorkerView>(
    workerViewSetting,
    WorkerView.TOGETHER,
  )

  return (
    <div className="card">
      <div className="card__header" style={{ marginBottom: "1rem" }}>
        Coverage
      </div>
      <div className="coverage-graph__tooltip" />
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
        <Toggle
          value={viewSetting}
          onChange={setWorkerView}
          options={workerViews.map(view => ({
            value: view,
            content: workerToggleContent[view].content,
            mobileContent: workerToggleContent[view].mobileContent,
          }))}
        />
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
