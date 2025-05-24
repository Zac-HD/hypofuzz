import { useEffect, useRef, useState, useMemo } from "react"
import * as d3 from "d3"
import { Report, Test, StatusCounts } from "../types/dashboard"
import { Toggle } from "./Toggle"
import { useSetting } from "../hooks/useSetting"
import { useNavigate } from "react-router-dom"
// import BoxSelect from "../assets/box-select.svg?react"

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
  report: Report
}

// in pixels
const distanceThreshold = 10

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
  x: d3.ScaleContinuousNumeric<number, number>
  y: d3.ScaleContinuousNumeric<number, number>
  g: d3.Selection<SVGGElement, unknown, null, undefined>
  zoom: d3.ZoomBehavior<SVGGElement, unknown>
  chartArea: d3.Selection<SVGGElement, unknown, null, undefined>
  navigate: (path: string) => void

  private tooltip: d3.Selection<HTMLDivElement, unknown, HTMLElement, any>
  private brush: d3.BrushBehavior<unknown> | null = null
  private eventListeners: Map<string, Array<() => void>> = new Map()
  private xAxis: d3.Selection<SVGGElement, unknown, null, undefined>
  private yAxis: d3.Selection<SVGGElement, unknown, null, undefined>
  private reportsColor: d3.ScaleOrdinal<string, string>
  private viewportX: d3.ScaleContinuousNumeric<number, number>
  private viewportY: d3.ScaleContinuousNumeric<number, number>

  constructor(
    svg: SVGSVGElement,
    reports: Map<string, GraphReport[]>,
    reportsColor: d3.ScaleOrdinal<string, string>,
    scaleSetting: string,
    axisSettingX: string,
    axisSettingY: string,
    navigate: (path: string) => void,
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
      axisSettingY == "behaviors" ? report.report.behaviors : report.report.fingerprints

    this.margin = { top: 20, right: 20, bottom: 45, left: 60 }
    this.width = svg.clientWidth - this.margin.left - this.margin.right
    this.height = 300 - this.margin.top - this.margin.bottom

    this.reportsColor = reportsColor
    const allReports = Array.from(reports.values()).flat()

    // symlog is like log but defined linearly in the range [0, 1].
    // https://d3js.org/d3-scale/symlog
    this.x = (scaleSetting === "log" ? d3.scaleSymlog() : d3.scaleLinear())
      .domain([0, d3.max(allReports, d => this.xValue(d)) || 1])
      .range([0, this.width])

    this.y = d3
      .scaleLinear()
      .domain([0, d3.max(allReports, d => this.yValue(d)) || 0])
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
      .call(
        d3
          .axisBottom(this.x)
          .ticks(5)
          .tickFormat(d => d.toLocaleString()),
      )

    this.yAxis = this.g.append("g").call(d3.axisLeft(this.y).ticks(5))

    this.g
      .append("text")
      .attr("transform", "rotate(-90)")
      .attr("y", 0 - this.margin.left)
      .attr("x", 0 - this.height / 2)
      .attr("dy", "1em")
      .style("text-anchor", "middle")
      .text(this.axisSettingY == "behaviors" ? "Behaviors" : "Fingerprints")

    this.g
      .append("text")
      .attr("x", this.width / 2)
      // - 5 is an unashamed hack to prevent clipping on characters that go
      // below the font baseline
      .attr("y", this.height + this.margin.bottom - 5)
      .style("text-anchor", "middle")
      .text(this.axisSettingX == "time" ? "Time (s)" : "Inputs")

    this.chartArea
      .on("mousemove", event => {
        const [mouseX, mouseY] = d3.pointer(event)
        let closestReport = null as GraphReport | null
        let closestDistance = Infinity

        Array.from(this.reports.values()).forEach(reports => {
          if (!reports || reports.length === 0) return

          reports
            .sortKey(report => [this.xValue(report)])
            .forEach(report => {
              const distance = Math.sqrt(
                (this.viewportX(this.xValue(report)) - mouseX) ** 2 +
                  (this.viewportY(this.yValue(report)) - mouseY) ** 2,
              )

              if (distance < closestDistance && distance < distanceThreshold) {
                closestDistance = distance
                closestReport = report
              }
            })
        })

        if (closestReport) {
          this.tooltip
            .style("display", "block")
            .style("left", `${event.pageX + 10}px`)
            .style("top", `${event.pageY - 10}px`).html(`
              <strong>${closestReport.nodeid.split("::").pop() || closestReport.nodeid}</strong><br/>
              ${closestReport.report.behaviors.toLocaleString()} behaviors / ${closestReport.report.fingerprints.toLocaleString()} fingerprints<br/>
              ${closestReport.report.ninputs.toLocaleString()} inputs / ${closestReport.report.elapsed_time.toFixed(1)} seconds
            `)
        } else {
          this.tooltip.style("display", "none")
        }
      })
      .on("mouseout", () => {
        this.tooltip.style("display", "none")
      })

    this.drawLines()
  }

  zoomTo(transform: d3.ZoomTransform, zoomY: boolean) {
    const x = transform.rescaleX(this.x)
    const y = zoomY ? transform.rescaleY(this.y) : this.y

    this.viewportX = x
    this.viewportY = y

    this.xAxis.call(
      d3
        .axisBottom(x)
        .ticks(5)
        .tickFormat(d => d.toLocaleString()),
    )

    if (zoomY) {
      this.yAxis.call(d3.axisLeft(y).ticks(5))
    }

    this.g.selectAll<SVGPathElement, GraphReport[]>(".chart-area path").attr(
      "d",
      d3
        .line<GraphReport>()
        .x(d => x(this.xValue(d)))
        .y(d => y(this.yValue(d))),
    )
  }

  drawLegend() {
    const legend = this.g
      .append("g")
      .attr("transform", `translate(${this.width + 10},0)`)

    this.reportsColor.domain().forEach((nodeid, i) => {
      const legendItem = legend
        .append("g")
        .attr("transform", `translate(0,${i * 20})`)
        .style("cursor", "pointer")
        .on("mouseover", () => {
          this.g
            .selectAll<SVGPathElement, GraphReport[]>("path")
            .filter(d => Array.isArray(d) && d.length > 0 && d[0].nodeid === nodeid)
            .classed("coverage-line__selected", true)
          d3.select(legendItem.node()).style("font-weight", "bold")
        })
        .on("mouseout", () => {
          this.g.selectAll("path").classed("coverage-line__selected", false)
          d3.select(legendItem.node()).style("font-weight", "normal")
        })
        .on("click", () => {
          this.navigate(`/tests/${encodeURIComponent(nodeid)}`)
        })

      legendItem
        .append("line")
        .attr("x1", 0)
        .attr("x2", 20)
        .attr("y1", 10)
        .attr("y2", 10)
        .attr("stroke", this.reportsColor(nodeid))

      legendItem
        .append("text")
        .attr("x", 25)
        .attr("y", 15)
        .text(nodeid.split("::").pop() || nodeid)
        .style("font-size", "12px")
    })
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
        .on("click", () => {
          this.navigate(`/tests/${encodeURIComponent(nodeid)}`)
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
    transform: d3.ZoomTransform | null
    zoomY: boolean
  }>({ transform: null, zoomY: false })
  const [boxSelectEnabled, setBoxSelectEnabled] = useState(false)
  const navigate = useNavigate()

  const reports = useMemo(() => {
    return new Map(
      Array.from(tests.entries()).map(([nodeid, test]) => {
        // zip up linear_status_counts, linear_elapsed_time, and linear_reports.
        const linearStatusCounts = test.linear_status_counts(null)
        const linearElapsedTime = test.linear_elapsed_time(null)
        const reports: GraphReport[] = []
        for (let i = 0; i < linearStatusCounts.length; i++) {
          reports.push({
            nodeid: nodeid,
            linear_status_counts: linearStatusCounts[i],
            linear_elapsed_time: linearElapsedTime[i],
            report: test.linear_reports[i],
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
    )

    if (zoomTransform.transform) {
      graph.zoom.transform(graph.chartArea, zoomTransform.transform)
    }

    graph.zoomTo(zoomTransform.transform ?? d3.zoomIdentity, zoomTransform.zoomY)

    graph.zoom.on(
      "zoom.saveTransform",
      (event: d3.D3ZoomEvent<SVGGElement, unknown>) => {
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
            { value: "behaviors", label: "Behaviors" },
            { value: "fingerprints", label: "Fingerprints" },
          ]}
        />
        <Toggle
          value={axisSettingX}
          onChange={setAxisSettingX}
          options={[
            { value: "inputs", label: "Inputs" },
            { value: "time", label: "Time" },
          ]}
        />
        <Toggle
          value={scaleSetting}
          onChange={setScaleSetting}
          options={[
            { value: "linear", label: "Linear" },
            { value: "log", label: "Log" },
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
