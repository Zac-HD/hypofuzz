import { useEffect, useRef, useState } from "react"
import * as d3 from "d3"
import { Report } from "../types/dashboard"
import { Toggle } from "./Toggle"
import { useSetting } from "../hooks/useSetting"
// import BoxSelect from "../assets/box-select.svg?react"

const mousePosition = { x: 0, y: 0 }
if (typeof window !== "undefined") {
  window.addEventListener("mousemove", e => {
    mousePosition.x = e.clientX
    mousePosition.y = e.clientY
  })
}

interface Props {
  reports: Record<string, Report[]>
}

// in pixels
const distanceThreshold = 10

class Graph {
  reports: Record<string, Report[]>
  scaleSetting: string
  axisSetting: string
  xValue: (d: Report) => number
  width: number
  height: number
  margin: { top: number; right: number; bottom: number; left: number }
  x: d3.ScaleContinuousNumeric<number, number>
  y: d3.ScaleContinuousNumeric<number, number>
  g: d3.Selection<SVGGElement, unknown, null, undefined>
  zoom: d3.ZoomBehavior<SVGGElement, unknown>
  chartArea: d3.Selection<SVGGElement, unknown, null, undefined>

  private tooltip: d3.Selection<HTMLDivElement, unknown, HTMLElement, any>
  private brush: d3.BrushBehavior<unknown> | null = null
  private eventListeners: Record<string, Array<() => void>> = {}
  private xAxis: d3.Selection<SVGGElement, unknown, null, undefined>
  private yAxis: d3.Selection<SVGGElement, unknown, null, undefined>
  private color: d3.ScaleOrdinal<string, string>
  private viewportX: d3.ScaleContinuousNumeric<number, number>
  private viewportY: d3.ScaleContinuousNumeric<number, number>

  constructor(
    svg: SVGSVGElement,
    reports: Record<string, Report[]>,
    scaleSetting: string,
    axisSetting: string,
  ) {
    this.reports = reports
    this.scaleSetting = scaleSetting
    this.axisSetting = axisSetting
    this.xValue = (d: Report) =>
      axisSetting == "time" ? d.elapsed_time : d.ninputs

    this.margin = { top: 20, right: 150, bottom: 45, left: 60 }
    this.width = svg.clientWidth - this.margin.left - this.margin.right
    this.height = 300 - this.margin.top - this.margin.bottom

    const nodeIds = Array.from(Object.keys(reports))
    this.color = d3.scaleOrdinal(d3.schemeCategory10).domain(nodeIds)
    const latests = Object.entries(reports).map(
      ([_, points]) => points[points.length - 1],
    )

    // symlog is like log but defined linearly in the range [0, 1].
    // https://d3js.org/d3-scale/symlog
    this.x = (scaleSetting === "log" ? d3.scaleSymlog() : d3.scaleLinear())
      .domain([0, d3.max(latests, d => this.xValue(d)) || 1])
      .range([0, this.width])

    this.y = d3
      .scaleLinear()
      .domain([0, d3.max(latests, d => d.branches) || 0])
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
      .text("Branches")

    this.g
      .append("text")
      .attr("x", this.width / 2)
      // - 5 is an unashamed hack to prevent clipping on characters that go
      // below the font baseline
      .attr("y", this.height + this.margin.bottom - 5)
      .style("text-anchor", "middle")
      .text(this.axisSetting == "time" ? "Time (s)" : "Inputs")

    this.chartArea
      .on("mousemove", event => {
        const [mouseX, mouseY] = d3.pointer(event)
        let closestPoint = null as Report | null
        let closestDistance = Infinity

        Object.values(this.reports).forEach(points => {
          if (!points || points.length === 0) return

          const sortedPoints = points.sort(
            (a, b) => this.xValue(a) - this.xValue(b),
          )

          sortedPoints.forEach(point => {
            const distance = Math.sqrt(
              (this.viewportX(this.xValue(point)) - mouseX) ** 2 +
                (this.viewportY(point.branches) - mouseY) ** 2,
            )

            if (distance < closestDistance && distance < distanceThreshold) {
              closestDistance = distance
              closestPoint = point
            }
          })
        })

        if (closestPoint) {
          this.tooltip
            .style("display", "block")
            .style("left", `${event.pageX + 10}px`)
            .style("top", `${event.pageY - 10}px`).html(`
              <strong>${closestPoint.nodeid.split("::").pop() || closestPoint.nodeid}</strong><br/>
              ${closestPoint.branches.toLocaleString()} branches<br/>
              ${closestPoint.ninputs.toLocaleString()} inputs / ${closestPoint.elapsed_time.toFixed(1)} seconds
            `)
        } else {
          this.tooltip.style("display", "none")
        }
      })
      .on("mouseout", () => {
        this.tooltip.style("display", "none")
      })

    this.drawLines()
    this.drawLegend()
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

    this.g.selectAll<SVGPathElement, Report[]>(".chart-area path").attr(
      "d",
      d3
        .line<Report>()
        .x(d => x(this.xValue(d)))
        .y(d => y(d.branches)),
    )
  }

  drawLegend() {
    const legend = this.g
      .append("g")
      .attr("transform", `translate(${this.width + 10},0)`)

    this.color.domain().forEach((nodeid, i) => {
      const legendItem = legend
        .append("g")
        .attr("transform", `translate(0,${i * 20})`)
        .style("cursor", "pointer")
        .on("mouseover", () => {
          this.g
            .selectAll<SVGPathElement, Report[]>("path")
            .filter(
              d => Array.isArray(d) && d.length > 0 && d[0].nodeid === nodeid,
            )
            .classed("coverage-line__selected", true)
          d3.select(legendItem.node()).style("font-weight", "bold")
        })
        .on("mouseout", () => {
          this.g.selectAll("path").classed("coverage-line__selected", false)
          d3.select(legendItem.node()).style("font-weight", "normal")
        })
        .on("click", () => {
          window.location.href = `/tests/${encodeURIComponent(nodeid)}`
        })

      legendItem
        .append("line")
        .attr("x1", 0)
        .attr("x2", 20)
        .attr("y1", 10)
        .attr("y2", 10)
        .attr("stroke", this.color(nodeid))

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
      .line<Report>()
      .x(d => this.x(this.xValue(d)))
      .y(d => this.y(d.branches))

    Object.entries(this.reports).forEach(([nodeid, points]) => {
      this.chartArea
        .append("path")
        .datum(points)
        .attr("fill", "none")
        .attr("stroke", this.color(nodeid))
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
          window.location.href = `/tests/${encodeURIComponent(nodeid)}`
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
    if (!this.eventListeners[eventName]) {
      this.eventListeners[eventName] = []
    }
    this.eventListeners[eventName].push(callback)
  }

  off(eventName: string, callback: () => void): void {
    if (!this.eventListeners[eventName]) return
    this.eventListeners[eventName] = this.eventListeners[eventName].filter(
      cb => cb !== callback,
    )
  }

  emit(eventName: string): void {
    if (!this.eventListeners[eventName]) {
      return
    }
    this.eventListeners[eventName].forEach(callback => callback())
  }
}

export function CoverageGraph({ reports }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [scaleSetting, setScaleSetting] = useSetting<string>(
    "graph_scale",
    "linear",
  )
  const [axisSetting, setAxisSetting] = useSetting<string>(
    "graph_x_axis",
    "time",
  )
  const [forceUpdate, setForceUpdate] = useState(true)
  const [zoomTransform, setZoomTransform] = useState<{
    transform: d3.ZoomTransform | null
    zoomY: boolean
  }>({ transform: null, zoomY: false })
  const [boxSelectEnabled, setBoxSelectEnabled] = useState(false)

  useEffect(() => {
    if (!svgRef.current || Object.keys(reports).length === 0) {
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
    const graph = new Graph(svgRef.current, reports, scaleSetting, axisSetting)

    if (zoomTransform.transform) {
      graph.zoom.transform(graph.chartArea, zoomTransform.transform)
    }

    graph.zoomTo(
      zoomTransform.transform ?? d3.zoomIdentity,
      zoomTransform.zoomY,
    )

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
  }, [reports, scaleSetting, axisSetting, forceUpdate, boxSelectEnabled])

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
          value={axisSetting}
          onChange={setAxisSetting}
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
