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
import { axisBottom as d3_axisBottom, axisLeft as d3_axisLeft } from "d3-axis"
import { brush as d3_brush, BrushBehavior } from "d3-brush"
import { Quadtree, quadtree as d3_quadtree } from "d3-quadtree"
import {
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
  scaleSymlog as d3_scaleSymlog,
} from "d3-scale"
import { ScaleContinuousNumeric, ScaleOrdinal } from "d3-scale"
import {
  interpolateViridis as d3_interpolateViridis,
  schemeCategory10 as d3_schemeCategory10,
} from "d3-scale-chromatic"
import { pointer as d3_pointer, select as d3_select, Selection } from "d3-selection"
import { line as d3_line } from "d3-shape"
import {
  D3ZoomEvent,
  zoom as d3_zoom,
  ZoomBehavior,
  zoomIdentity as d3_zoomIdentity,
  ZoomTransform,
} from "d3-zoom"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

// import BoxSelect from "../assets/box-select.svg?react"
import LinearScaleIcon from "../assets/linear-scale.svg?react"
import LogScaleIcon from "../assets/log-scale.svg?react"
import { useIsMobile } from "../hooks/useIsMobile"
import { useSetting } from "../hooks/useSetting"
import { StatusCounts } from "../types/dashboard"
import { Report } from "../types/dashboard"
import { Test } from "../types/test"
import { max, min, navigateOnClick, readableNodeid } from "../utils/utils"
import { Toggle } from "./Toggle"

const d3 = {
  scaleSymlog: d3_scaleSymlog,
  scaleLinear: d3_scaleLinear,
  select: d3_select,
  zoom: d3_zoom,
  zoomIdentity: d3_zoomIdentity,
  pointer: d3_pointer,
  line: d3_line,
  axisBottom: d3_axisBottom,
  axisLeft: d3_axisLeft,
  brush: d3_brush,
  scaleOrdinal: d3_scaleOrdinal,
  schemeCategory10: d3_schemeCategory10,
  interpolateViridis: d3_interpolateViridis,
  quadtree: d3_quadtree,
}

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

class GraphReport {
  constructor(
    public nodeid: string,
    public linear_status_counts: StatusCounts,
    public linear_elapsed_time: number,
    public behaviors: number,
    public fingerprints: number,
  ) {}

  static fromReport(nodeid: string, report: Report): GraphReport {
    return new GraphReport(
      nodeid,
      report.status_counts,
      report.elapsed_time,
      report.behaviors,
      report.fingerprints,
    )
  }
}

interface GraphLine {
  url: string | null
  reports: GraphReport[]
  color: string
}

// in pixels
const distanceThreshold = 10
const graphHeight = 270

class Graph {
  lines: GraphLine[]
  scaleSetting: string
  scaleSettingY: string
  axisSettingX: string
  axisSettingY: string
  xValue: (d: GraphReport) => number
  yValue: (d: GraphReport) => number
  width: number
  height: number
  margin: { top: number; right: number; bottom: number; left: number }
  x: ScaleContinuousNumeric<number, number>
  y: ScaleContinuousNumeric<number, number>
  g: Selection<SVGGElement, unknown, null, undefined>
  zoom: ZoomBehavior<SVGGElement, unknown>
  chartArea: Selection<SVGGElement, unknown, null, undefined>
  navigate: (path: string) => void

  private tooltip: Selection<HTMLDivElement, unknown, HTMLElement, any>
  private brush: BrushBehavior<unknown> | null = null
  private eventListeners: Map<string, Array<() => void>> = new Map()
  private xAxis: Selection<SVGGElement, unknown, null, undefined>
  private yAxis: Selection<SVGGElement, unknown, null, undefined>
  private reportsColor: ScaleOrdinal<string, string>
  private viewportX: ScaleContinuousNumeric<number, number>
  private viewportY: ScaleContinuousNumeric<number, number>
  private quadtree!: Quadtree<GraphReport>

  constructor(
    svg: SVGSVGElement,
    lines: GraphLine[],
    reportsColor: ScaleOrdinal<string, string>,
    scaleSetting: string,
    scaleSettingY: string,
    axisSettingX: string,
    axisSettingY: string,
    navigate: (path: string) => void,
    isMobile: boolean,
  ) {
    this.lines = lines
    this.scaleSetting = scaleSetting
    this.scaleSettingY = scaleSettingY
    this.axisSettingX = axisSettingX
    this.axisSettingY = axisSettingY
    this.navigate = navigate
    this.xValue = (report: GraphReport) =>
      axisSettingX == "time"
        ? report.linear_elapsed_time
        : report.linear_status_counts.sum()
    this.yValue = (report: GraphReport) =>
      axisSettingY == "behaviors" ? report.behaviors : report.fingerprints

    this.margin = {
      top: 5,
      right: 5,
      bottom: 25,
      left: 40,
    }
    this.width = svg.clientWidth - this.margin.left - this.margin.right
    this.height = graphHeight - this.margin.top - this.margin.bottom

    this.reportsColor = reportsColor
    const allReports = lines.map(line => line.reports).flat()

    // symlog is like log but defined linearly in the range [0, 1].
    // https://d3js.org/d3-scale/symlog
    this.x = (scaleSetting === "log" ? d3.scaleSymlog() : d3.scaleLinear())
      .domain([0, max(allReports.map(r => this.xValue(r))) || 1])
      .range([0, this.width])

    this.y = (scaleSettingY === "log" ? d3.scaleSymlog() : d3.scaleLinear())
      .domain([0, max(allReports.map(r => this.yValue(r))) || 0])
      .range([this.height, 0])

    // this.x and this.y are the full axes which encompass all of the points.
    // this.viewportX and this.viewportY are the current visible axes, because
    // e.g. the axis has been zoomed. We set this in zoomTo.
    this.viewportX = this.x
    this.viewportY = this.y

    this.g = d3
      .select(svg)
      .append("g")
      .attr("transform", `translate(${this.margin.left},${this.margin.top})`)

    this.g
      .append("defs")
      .append("clipPath")
      .attr("id", "clip")
      .append("rect")
      .attr("width", this.width)
      .attr("height", this.height + 5)
      .attr("x", 0)
      // worth tracking this down at some point, top clips some points
      // otherwise when it shouldn't
      // (and if you do track this down, remove the corresponding + 5 above)
      .attr("y", -5)

    this.chartArea = this.g
      .append("g")
      .attr("class", "chart-area")
      .attr("clip-path", "url(#clip)")

    this.chartArea
      .append("rect")
      .attr("width", this.width)
      .attr("height", this.height)
      .attr("fill", "none")
      .attr("pointer-events", "all")

    this.zoom = d3
      .zoom<SVGGElement, unknown>()
      .scaleExtent([1, Infinity])
      .on("zoom", event => this.zoomTo(event.transform, false))
    this.chartArea.call(this.zoom as any)

    // reset to original viewport on doubleclick
    this.chartArea.on("dblclick.zoom", () => {
      this.chartArea
        .transition()
        .duration(500)
        .call(this.zoom.transform, d3.zoomIdentity)
    })

    this.tooltip = d3.select(".coverage-graph__tooltip")
    this.xAxis = this.g
      .append("g")
      .attr("transform", `translate(0,${this.height})`)
      .call(this.createXAxis(this.x))

    this.yAxis = this.g.append("g").call(this.createYAxis(this.y))

    this.chartArea
      .on("mousemove", event => {
        const [mouseX, mouseY] = d3.pointer(event)
        const closestReport = this.quadtree.find(mouseX, mouseY, distanceThreshold)

        if (closestReport) {
          this.tooltip
            .style("display", "block")
            .style("left", `${event.pageX + 10}px`)
            .style("top", `${event.pageY - 10}px`).html(`
              <strong>${readableNodeid(closestReport.nodeid)}</strong><br/>
              ${closestReport.behaviors.toLocaleString()} behaviors / ${closestReport.fingerprints.toLocaleString()} fingerprints<br/>
              ${closestReport.linear_status_counts.sum().toLocaleString()} inputs / ${closestReport.linear_elapsed_time.toFixed(1)} seconds
            `)
        } else {
          this.tooltip.style("display", "none")
        }
      })
      .on("mouseout", () => {
        this.tooltip.style("display", "none")
      })

    this.drawLines()
    this.updateQuadtree()
  }

  private logAxis(axis: any, maxValue: number) {
    const tickValues = [0]
    let power = 1
    while (power <= maxValue) {
      tickValues.push(power)
      power *= 10
    }

    return axis.tickValues(tickValues).tickFormat((d: any) => {
      const num = d.valueOf()
      console.assert(num >= 0)
      if (num >= 1_000_000) {
        return `${Math.floor(num / 1_000_000)}M`
      } else if (num >= 1000) {
        return `${Math.floor(num / 1000)}k`
      } else if (num > 0) {
        return num.toLocaleString()
      } else {
        return "0"
      }
    })
  }

  private createXAxis(scale: ScaleContinuousNumeric<number, number>) {
    if (this.scaleSetting === "log") {
      const maxValue = scale.domain()[1]
      return this.logAxis(d3.axisBottom(scale), maxValue)
    } else {
      return d3
        .axisBottom(scale)
        .ticks(5)
        .tickFormat(d => d.toLocaleString())
    }
  }

  private createYAxis(scale: ScaleContinuousNumeric<number, number>) {
    if (this.scaleSettingY === "log") {
      const maxValue = scale.domain()[1]
      return this.logAxis(d3.axisLeft(scale), maxValue)
    } else {
      return d3.axisLeft(scale).ticks(5)
    }
  }

  private updateQuadtree() {
    const allReports = this.lines.map(line => line.reports).flat()
    this.quadtree = d3
      .quadtree<GraphReport>()
      .x(d => this.viewportX(this.xValue(d)))
      .y(d => this.viewportY(this.yValue(d)))
      .addAll(allReports)
  }

  zoomTo(transform: ZoomTransform, zoomY: boolean) {
    const x = transform.rescaleX(this.x)
    const y = zoomY ? transform.rescaleY(this.y) : this.y

    this.viewportX = x
    this.viewportY = y

    this.xAxis.call(this.createXAxis(x))

    if (zoomY) {
      this.yAxis.call(this.createYAxis(y))
    }

    this.g.selectAll<SVGPathElement, GraphReport[]>(".chart-area path").attr(
      "d",
      d3
        .line<GraphReport>()
        .x(d => x(this.xValue(d)))
        .y(d => y(this.yValue(d))),
    )

    this.updateQuadtree()
  }

  drawLines() {
    const d3Line = d3
      .line<GraphReport>()
      .x(d => this.x(this.xValue(d)))
      .y(d => this.y(this.yValue(d)))

    this.lines.forEach(line => {
      this.chartArea
        .append("path")
        .datum(line.reports)
        .attr("fill", "none")
        .attr("stroke", line.color)
        .attr("d", d3Line)
        .attr("class", "coverage-line")
        .style("cursor", "pointer")
        .on("mouseover", function () {
          d3.select(this).classed("coverage-line__selected", true)
        })
        .on("mouseout", function () {
          d3.select(this).classed("coverage-line__selected", false)
        })
        .on("click", event => {
          if (line.url) {
            navigateOnClick(event, line.url, this.navigate)
          }
        })
    })
  }

  enableBoxBrush() {
    // disable regular zoom behavior so it doesn't steal our mousedowns.
    // make sure not to disable the entire .zoom namespace, which also
    // disables dblclick.zoom
    for (const event of ["wheel", "mousedown", "mousemove", "mouseup"]) {
      this.chartArea.on(`${event}.zoom`, null)
    }

    this.brush = d3
      .brush()
      .extent([
        [0, 0],
        [this.width, this.height],
      ])
      .on("end", event => {
        if (!event.selection) {
          return
        }
        const [[x0, y0], [x1, y1]] = event.selection as [
          [number, number],
          [number, number],
        ]
        this.chartArea.call(this.brush!.clear)
        this.chartArea.call(this.zoom as any)

        // ignore selections which are too small
        if (Math.abs(x1 - x0) < 5 || Math.abs(y1 - y0) < 5) {
          this.emit("boxSelectEnd")
          return
        }

        const xScale = this.width / (x1 - x0)
        const yScale = this.height / (y1 - y0)
        // change to Math.min to avoid cropping data when aspect ratio doesn't match
        // TODO we should just lock the brush aspect ratio when drawing
        const scale = Math.max(xScale, yScale)
        const transform = d3.zoomIdentity
          .translate(this.width / 2, this.height / 2)
          .scale(scale)
          .translate(-(x0 + x1) / 2, -(y0 + y1) / 2)

        this.chartArea
          .transition()
          .duration(250)
          .call(this.zoom.transform, transform)
          .on("end", () => {
            this.emit("boxSelectEnd")
          })
      })

    this.chartArea.style("cursor", "crosshair").call(this.brush)
  }

  cleanup() {
    this.tooltip.style("display", "none")
    this.g.selectAll("path").classed("coverage-line__selected", false)
  }

  // handroll a small event system

  on(eventName: string, callback: () => void): void {
    if (!this.eventListeners.has(eventName)) {
      this.eventListeners.set(eventName, [])
    }
    this.eventListeners.get(eventName)!.push(callback)
  }

  off(eventName: string, callback: () => void): void {
    if (!this.eventListeners.has(eventName)) return
    this.eventListeners.set(
      eventName,
      this.eventListeners.get(eventName)!.filter(cb => cb !== callback),
    )
  }

  emit(eventName: string): void {
    if (!this.eventListeners.has(eventName)) {
      return
    }
    this.eventListeners.get(eventName)!.forEach(callback => callback())
  }
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

export function CoverageGraph({
  tests,
  filterString = "",
  testsLoaded,
  workers_after = null,
  workerViews = [WorkerView.TOGETHER, WorkerView.SEPARATE, WorkerView.LATEST],
  workerViewSetting,
}: Props) {
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
  const [viewSetting, setWorkerView] = useSetting<WorkerView>(
    workerViewSetting,
    WorkerView.TOGETHER,
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
      function viridisColor(timestamp: number) {
        if (timestamps.length <= 1) {
          return d3.interpolateViridis(0.5) // Use middle color if only one worker
        }
        const normalized = (timestamp - minTimestamp) / (maxTimestamp - minTimestamp)
        return d3.interpolateViridis(normalized)
      }

      for (const [nodeid, test] of tests.entries()) {
        for (const workerReports of test.reports_by_worker.values()) {
          if (workerReports.length > 0) {
            lines.push({
              url: null,
              reports: workerReports.map(report =>
                GraphReport.fromReport(nodeid, report),
              ),
              color: viridisColor(workerReports[0].timestamp),
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
  }, [tests, workers_after, viewSetting])

  const filteredLines = useMemo(() => {
    if (!filterString) return lines
    return lines.filter(line =>
      line.url?.toLowerCase().includes(filterString.toLowerCase()),
    )
  }, [lines, filterString])

  useEffect(() => {
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
      reportsColor,
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

    graph.zoom.on("zoom.saveTransform", (event: D3ZoomEvent<SVGGElement, unknown>) => {
      setZoomTransform({ transform: event.transform, zoomY: false })
    })

    if (boxSelectEnabled) {
      graph.enableBoxBrush()
    }

    graph.on("boxSelectEnd", toggleBoxSelect)

    return () => {
      graph.cleanup()
    }
  }, [
    tests,
    scaleSettingX,
    scaleSettingY,
    axisSettingX,
    axisSettingY,
    viewSetting,
    forceUpdate,
    boxSelectEnabled,
    navigate,
  ])

  const toggleBoxSelect = () => {
    setBoxSelectEnabled(!boxSelectEnabled)
    setForceUpdate(true)
  }

  return (
    <div className="card">
      <div className="card__header" style={{ marginBottom: "1rem" }}>
        Coverage
      </div>
      <div className="coverage-graph__tooltip" />
      <div
        style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}
      >
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
          <svg
            className="coverage-graph__svg"
            ref={svgRef}
            style={{ width: "100%", height: `${graphHeight}px` }}
            onMouseEnter={() => setCurrentlyHovered(true)}
            onMouseLeave={() => {
              setCurrentlyHovered(false)
              setForceUpdate(true)
            }}
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
