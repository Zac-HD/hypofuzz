import "d3-transition"

import { axisBottom as d3_axisBottom, axisLeft as d3_axisLeft } from "d3-axis"
import { brush as d3_brush, BrushBehavior } from "d3-brush"
import { Quadtree, quadtree as d3_quadtree } from "d3-quadtree"
import {
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
  scaleSymlog as d3_scaleSymlog,
} from "d3-scale"
import { ScaleContinuousNumeric } from "d3-scale"
import {
  interpolateViridis as d3_interpolateViridis,
  schemeCategory10 as d3_schemeCategory10,
} from "d3-scale-chromatic"
import { pointer as d3_pointer, select as d3_select, Selection } from "d3-selection"
import { line as d3_line } from "d3-shape"
import {
  zoom as d3_zoom,
  ZoomBehavior,
  zoomIdentity as d3_zoomIdentity,
  ZoomTransform,
} from "d3-zoom"
import { Report, StatusCounts } from "src/types/dashboard"
import { max, navigateOnClick, readableNodeid } from "src/utils/utils"

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

export class GraphReport {
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

export interface GraphLine {
  url: string | null
  reports: GraphReport[]
  color: string
}

// in pixels
const distanceThreshold = 10
export const GRAPH_HEIGHT = 270
const XAXIS_CLIP_MARGIN = 5

export class Graph {
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
  private viewportX: ScaleContinuousNumeric<number, number>
  private viewportY: ScaleContinuousNumeric<number, number>
  private quadtree!: Quadtree<GraphReport>

  constructor(
    svg: SVGSVGElement,
    lines: GraphLine[],
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
    this.height = GRAPH_HEIGHT - this.margin.top - this.margin.bottom

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

    const defs = this.g.append("defs")

    defs
      .append("clipPath")
      .attr("id", "clip-content")
      .append("rect")
      .attr("width", this.width)
      .attr("height", this.height + 5)
      .attr("x", 0)
      // worth tracking this down at some point, top clips some points
      // otherwise when it shouldn't
      // (and if you do track this down, remove the corresponding + 5 above)
      .attr("y", -5)

    // clip for the x axis is slightly larger than for the graph content, to avoid left/rightmost
    // axis ticks being clipped in the identity zoom
    defs
      .append("clipPath")
      .attr("id", "clip-x-axis")
      .append("rect")
      .attr("width", this.width + XAXIS_CLIP_MARGIN * 2)
      .attr("height", this.height)
      .attr("x", -XAXIS_CLIP_MARGIN)
      .attr("y")

    this.chartArea = this.g
      .append("g")
      .attr("class", "chart-area")
      .attr("clip-path", "url(#clip-content)")

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
      .attr("clip-path", "url(#clip-x-axis)")
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
