import "d3-transition"

import {
  faClock,
  faCodeBranch,
  faFingerprint,
  faHashtag,
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
import { schemeCategory10 as d3_schemeCategory10 } from "d3-scale-chromatic"
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

import { useIsMobile } from "../hooks/useIsMobile"
import { useSetting } from "../hooks/useSetting"
import { StatusCounts, Test } from "../types/dashboard"
import { max } from "../utils/utils"
import { Toggle } from "./Toggle"
// import BoxSelect from "../assets/box-select.svg?react"

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
  quadtree: d3_quadtree,
}

const mousePosition = { x: 0, y: 0 }
if (typeof window !== "undefined") {
  window.addEventListener("mousemove", e => {
    mousePosition.x = e.clientX
    mousePosition.y = e.clientY
  })
}

interface Props {
  tests: Map<string, Test>
  filterString?: string
}

interface GraphReport {
  nodeid: string
  linear_status_counts: StatusCounts
  linear_elapsed_time: number
  behaviors: number
  fingerprints: number
  ninputs: number
  elapsed_time: number
}

// in pixels
const distanceThreshold = 10

function prependIcon(
  textElement: Selection<SVGTextElement, unknown, null, undefined>,
  icon: any,
  direction: "vertical" | "horizontal" = "horizontal",
  iconSize: number = 12,
  iconPadding: number = 6,
) {
  const textBBox = (textElement.node() as SVGTextElement).getBBox()
  const parentGroup = d3.select(
    (textElement.node() as SVGTextElement).parentNode as SVGGElement,
  )

  let iconX: number
  let iconY: number

  if (direction === "vertical") {
    iconX = textBBox.x - iconSize - iconPadding
    iconY = textBBox.y + (textBBox.height - iconSize) / 2
  } else {
    iconX = textBBox.x - iconSize - iconPadding
    iconY = textBBox.y + (textBBox.height - iconSize) / 2
  }

  parentGroup
    .append("svg")
    .attr("x", iconX)
    .attr("y", iconY)
    .attr("width", iconSize)
    .attr("height", iconSize)
    .attr("viewBox", `0 0 ${icon.icon[0]} ${icon.icon[1]}`)
    .append("path")
    .attr("d", icon.icon[4] as string)
}

class Graph {
  reports: Map<string, GraphReport[]>
  scaleSetting: string
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
    reports: Map<string, GraphReport[]>,
    reportsColor: ScaleOrdinal<string, string>,
    scaleSetting: string,
    axisSettingX: string,
    axisSettingY: string,
    navigate: (path: string) => void,
    isMobile: boolean,
  ) {
    this.reports = reports
    this.scaleSetting = scaleSetting
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
      top: 20,
      right: 20,
      bottom: isMobile ? 40 : 45,
      left: isMobile ? 50 : 60,
    }
    this.width = svg.clientWidth - this.margin.left - this.margin.right
    this.height = 300 - this.margin.top - this.margin.bottom

    this.reportsColor = reportsColor
    const allReports = Array.from(reports.values()).flat()

    // symlog is like log but defined linearly in the range [0, 1].
    // https://d3js.org/d3-scale/symlog
    this.x = (scaleSetting === "log" ? d3.scaleSymlog() : d3.scaleLinear())
      .domain([0, max(allReports, d => this.xValue(d)) || 1])
      .range([0, this.width])

    this.y = d3
      .scaleLinear()
      .domain([0, max(allReports, d => this.yValue(d)) || 0])
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

    const yAxisGroup = this.g
      .append("g")
      .attr(
        "transform",
        `translate(${-this.margin.left}, ${this.height / 2}) rotate(-90)`,
      )

    const yIcon = this.axisSettingY == "behaviors" ? faCodeBranch : faFingerprint
    const yLabelText = this.axisSettingY == "behaviors" ? "Behaviors" : "Fingerprints"
    const yTextElement = yAxisGroup
      .append("text")
      .attr("x", 0)
      .attr("y", 0)
      .attr("dy", "1em")
      .style("text-anchor", "middle")
      .text(yLabelText)

    prependIcon(yTextElement, yIcon, "vertical")

    const xIcon = this.axisSettingX == "time" ? faClock : faHashtag
    const xLabelText = this.axisSettingX == "time" ? "Time (s)" : "Inputs"
    const xTextElement = this.g
      .append("text")
      .attr("x", this.width / 2)
      // - 5 is an unashamed hack to prevent clipping on characters that go
      // below the font baseline
      .attr("y", this.height + this.margin.bottom - 5)
      .style("text-anchor", "middle")
      .text(xLabelText)

    prependIcon(xTextElement, xIcon, "horizontal")

    this.chartArea
      .on("mousemove", event => {
        const [mouseX, mouseY] = d3.pointer(event)
        const closestReport = this.quadtree.find(mouseX, mouseY, distanceThreshold)

        if (closestReport) {
          this.tooltip
            .style("display", "block")
            .style("left", `${event.pageX + 10}px`)
            .style("top", `${event.pageY - 10}px`).html(`
              <strong>${closestReport.nodeid.split("::").pop() || closestReport.nodeid}</strong><br/>
              ${closestReport.behaviors.toLocaleString()} behaviors / ${closestReport.fingerprints.toLocaleString()} fingerprints<br/>
              ${closestReport.ninputs.toLocaleString()} inputs / ${closestReport.elapsed_time.toFixed(1)} seconds
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

  private createXAxis(scale: ScaleContinuousNumeric<number, number>) {
    if (this.scaleSetting === "log") {
      const maxValue = scale.domain()[1]
      const tickValues = [0]

      let power = 1
      while (power <= maxValue) {
        tickValues.push(power)
        power *= 10
      }

      return d3
        .axisBottom(scale)
        .tickValues(tickValues)
        .tickFormat(d => {
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
    } else {
      return d3
        .axisBottom(scale)
        .ticks(5)
        .tickFormat(d => d.toLocaleString())
    }
  }

  private createYAxis(scale: ScaleContinuousNumeric<number, number>) {
    return d3.axisLeft(scale).ticks(5)
  }

  private updateQuadtree() {
    const allReports = Array.from(this.reports.values()).flat()
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
    const line = d3
      .line<GraphReport>()
      .x(d => this.x(this.xValue(d)))
      .y(d => this.y(this.yValue(d)))

    Array.from(this.reports.entries()).forEach(([nodeid, reports]) => {
      this.chartArea
        .append("path")
        .datum(reports)
        .attr("fill", "none")
        .attr("stroke", this.reportsColor(nodeid))
        .attr("d", line)
        .attr("class", "coverage-line")
        .style("cursor", "pointer")
        .on("mouseover", function () {
          d3.select(this).classed("coverage-line__selected", true)
        })
        .on("mouseout", function () {
          d3.select(this).classed("coverage-line__selected", false)
        })
        .on("click", event => {
          if (event.metaKey || event.ctrlKey) {
            window.open(`/tests/${encodeURIComponent(nodeid)}`, "_blank")
          } else {
            this.navigate(`/tests/${encodeURIComponent(nodeid)}`)
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

export function CoverageGraph({ tests, filterString = "" }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [scaleSetting, setScaleSetting] = useSetting<"log" | "linear">(
    "graph_scale",
    "log",
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

  const reports = useMemo(() => {
    return new Map(
      Array.from(tests.entries())
        // deterministic line color ordering, regardless of insertion order (which might vary
        // based on websocket arrival order)
        //
        // we may also want a deterministic mapping of hash(nodeid) -> color, so the color is stable
        // even across pages (overview vs individual test) or after a new test is added? But maybe we
        // *don't* want this. I'm not sure which is better ux. A graph with only one line and having
        // a non-blue color is weird.
        .sortKey(([nodeid, test]) => nodeid)
        .map(([nodeid, test]) => {
          // zip up linear_status_counts, linear_elapsed_time, and linear_reports.
          const linearStatusCounts = test.linear_status_counts(null)
          const linearElapsedTime = test.linear_elapsed_time(null)
          const reports: GraphReport[] = []
          for (let i = 0; i < linearStatusCounts.length; i++) {
            const report = test.linear_reports[i]
            reports.push({
              nodeid: nodeid,
              linear_status_counts: linearStatusCounts[i],
              linear_elapsed_time: linearElapsedTime[i],
              behaviors: report.behaviors,
              fingerprints: report.fingerprints,
              ninputs: report.ninputs,
              elapsed_time: report.elapsed_time,
            })
          }
          return [nodeid, reports]
        }),
    )
  }, [tests])

  const filteredReports = useMemo(() => {
    if (!filterString) return reports
    return new Map(
      Array.from(reports.entries()).filter(([nodeid]) =>
        nodeid.toLowerCase().includes(filterString.toLowerCase()),
      ),
    )
  }, [reports, filterString])

  // use the unfiltered reports as the domain so colors are stable across filtering.
  const reportsColor = d3.scaleOrdinal(d3.schemeCategory10).domain(reports.keys())

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
    const svgRect = svgRef.current!.getBoundingClientRect()
    if (
      !forceUpdate &&
      mousePosition.x >= svgRect.left &&
      mousePosition.x <= svgRect.right &&
      mousePosition.y >= svgRect.top &&
      mousePosition.y <= svgRect.bottom
    ) {
      return
    }

    if (forceUpdate) {
      setForceUpdate(false)
    }

    d3.select(svgRef.current).selectAll("*").remove()
    const graph = new Graph(
      svgRef.current,
      filteredReports,
      reportsColor,
      scaleSetting,
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
    filteredReports,
    scaleSetting,
    axisSettingX,
    axisSettingY,
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
      <div className="card__header">Coverage</div>
      <div className="coverage-graph__controls">
        {/* box selection has issues with zoom viewport, temporarily disabling
        <div
          className={`coverage-graph__icon ${boxSelectEnabled ? "coverage-graph__icon--active" : ""}`}
          onClick={toggleBoxSelect}
        >
          <BoxSelect width="16" height="16" />
        </div> */}
        <Toggle
          value={axisSettingY}
          onChange={setAxisSettingY}
          options={[
            {
              value: "behaviors",
              content: (
                <>
                  <FontAwesomeIcon icon={faCodeBranch} /> Behaviors
                </>
              ),
              mobileContent: <FontAwesomeIcon icon={faCodeBranch} />,
            },
            {
              value: "fingerprints",
              content: (
                <>
                  <FontAwesomeIcon icon={faFingerprint} /> Fingerprints
                </>
              ),
              mobileContent: <FontAwesomeIcon icon={faFingerprint} />,
            },
          ]}
        />
        <Toggle
          value={axisSettingX}
          onChange={setAxisSettingX}
          options={[
            {
              value: "inputs",
              content: (
                <>
                  <FontAwesomeIcon icon={faHashtag} /> Inputs
                </>
              ),
              mobileContent: <FontAwesomeIcon icon={faHashtag} />,
            },
            {
              value: "time",
              content: (
                <>
                  <FontAwesomeIcon icon={faClock} /> Time
                </>
              ),
              mobileContent: <FontAwesomeIcon icon={faClock} />,
            },
          ]}
        />
        <Toggle
          value={scaleSetting}
          onChange={setScaleSetting}
          options={[
            { value: "linear", content: "Linear" },
            { value: "log", content: "Log" },
          ]}
        />
      </div>
      <div className="coverage-graph__tooltip" />
      <svg
        className="coverage-graph__svg"
        ref={svgRef}
        style={{ width: "100%", height: "300px" }}
      />
    </div>
  )
}
