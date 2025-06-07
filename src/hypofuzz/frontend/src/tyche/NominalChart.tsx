import { useEffect, useRef } from "react"
import { Observation } from "../types/dashboard"
import { sum, setsEqual, max } from "../utils/utils"
import { TYCHE_COLOR } from "./Tyche"
import { select as d3_select } from "d3-selection"
import {
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
  scaleBand as d3_scaleBand,
} from "d3-scale"
import { axisBottom as d3_axisBottom, axisLeft as d3_axisLeft } from "d3-axis"

const d3 = {
  select: d3_select,
  scaleLinear: d3_scaleLinear,
  scaleOrdinal: d3_scaleOrdinal,
  scaleBand: d3_scaleBand,
  axisBottom: d3_axisBottom,
  axisLeft: d3_axisLeft,
}

type NominalChartProps = {
  feature: string
  observations: Observation[]
}

const PRESENT_STRING = "Present"
const NOT_PRESENT_STRING = "Not present"
const HORIZONTAL_BAR_FEATURE_CUTOFF = 5

export function NominalChart({ feature, observations }: NominalChartProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  observations = observations.filter(obs => obs.status !== "gave_up")

  useEffect(() => {
    if (!parentRef.current || !svgRef.current || observations.length === 0) {
      return
    }

    // feature: count
    let data = new Map<string, number>()

    for (const observation of observations) {
      const featureValue = observation.features.get(feature)
      let label
      if (featureValue === undefined) {
        label = NOT_PRESENT_STRING
      } else if (featureValue === "") {
        label = PRESENT_STRING
      } else {
        label = featureValue
      }
      if (data.has(label)) {
        data.set(label, data.get(label)! + 1)
      } else {
        data.set(label, 1)
      }
    }
    const total = sum(Array.from(data.values()))

    data = new Map(
      [...data.entries()].sortKey(([feature, _count]) => {
        if (feature === PRESENT_STRING) return 0
        if (feature === NOT_PRESENT_STRING) return 1
        return feature
      }),
    )

    d3.select(svgRef.current).selectAll("*").remove()

    const width = parentRef.current.clientWidth
    const height = data.size < HORIZONTAL_BAR_FEATURE_CUTOFF ? 85 : 170

    const svg = d3
      .select(svgRef.current)
      .attr("width", width)
      .attr("height", height)
      .append("g")

    const tooltipDiv = d3
      .select("body")
      .append("div")
      .attr("class", "tyche-tooltip")
      .style("opacity", 0)
      .style("position", "absolute")
      .style("background-color", "rgba(0, 0, 0, 0.8)")
      .style("color", "white")
      .style("border-radius", "4px")
      .style("padding", "8px")
      .style("font-size", "12px")
      .style("pointer-events", "none")
      .style("z-index", "10")

    const showTooltip = function (event: MouseEvent, d: [string, number]) {
      const [label, count] = d
      tooltipDiv
        .style("opacity", 1)
        .html(`${feature}<br>${label}: ${count}`)
        .style("left", `${event.pageX + 10}px`)
        .style("top", `${event.pageY - 28}px`)
    }

    const moveTooltip = function (event: MouseEvent) {
      tooltipDiv
        .style("left", `${event.pageX + 10}px`)
        .style("top", `${event.pageY - 28}px`)
    }

    const hideTooltip = function () {
      tooltipDiv.style("opacity", 0)
    }

    // use a horizontally-stacked bar chart for 1-4 different feature labels,
    // and a standard histogram otherwise
    if (data.size < HORIZONTAL_BAR_FEATURE_CUTOFF) {
      const margin = { top: 0, right: 15, bottom: 20, left: 15 }
      const innerWidth = width - margin.left - margin.right
      const innerHeight = height - margin.top - margin.bottom

      const x = d3.scaleLinear().domain([0, 1]).range([0, innerWidth])

      let colorScale: (feature: string) => string
      if (
        setsEqual(
          new Set(Array.from(data.keys())),
          new Set([PRESENT_STRING, NOT_PRESENT_STRING]),
        )
      ) {
        colorScale = (feature: string) => {
          if (feature === PRESENT_STRING) return TYCHE_COLOR.SUCCESS
          if (feature === NOT_PRESENT_STRING) return TYCHE_COLOR.ERROR
          return TYCHE_COLOR.PRIMARY
        }
      } else {
        colorScale = d3
          .scaleOrdinal<string>()
          .domain(Array.from(data.keys()))
          .range([
            TYCHE_COLOR.PRIMARY,
            TYCHE_COLOR.ACCENT,
            TYCHE_COLOR.ACCENT2,
            TYCHE_COLOR.ACCENT3,
            TYCHE_COLOR.ACCENT4,
          ])
      }

      const g = svg
        .append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`)

      let xAccumulator = 0
      const barHeight = innerHeight - margin.bottom

      data.forEach((count, feature) => {
        const barWidth = (count / total) * innerWidth

        g.append("rect")
          .attr("x", xAccumulator)
          .attr("y", 0)
          .attr("width", barWidth)
          .attr("height", barHeight)
          .attr("fill", colorScale(feature))
          .style("opacity", 1)
          .on("mouseover", event => showTooltip(event, [feature, count]))
          .on("mousemove", moveTooltip)
          .on("mouseleave", hideTooltip)

        g.append("text")
          .attr("x", xAccumulator + barWidth / 2)
          .attr("y", barHeight / 2)
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("fill", "white")
          .text(feature)
          .style("font-size", "12px")

        xAccumulator += barWidth
      })

      g.append("g")
        .attr("transform", `translate(0,${barHeight})`)
        .call(d3.axisBottom(x).tickFormat(d => `${Math.round(Number(d) * 100)}%`))

      g.append("text")
        .attr("x", innerWidth / 2)
        .attr("y", barHeight + 30)
        .attr("text-anchor", "middle")
        .text("% of observations")
        .style("font-size", "12px")
    } else {
      // add some margin inset for the graph proper so the axes don't get cut off
      const margin = { top: 5, right: 5, bottom: 30, left: 30 }
      const innerWidth = width - margin.left - margin.right
      const innerHeight = height - margin.top - margin.bottom

      const x = d3
        .scaleBand()
        .domain(Array.from(data.keys()))
        .range([0, innerWidth])
        .padding(0.2)

      const y = d3
        .scaleLinear()
        .domain([0, max(Array.from(data.values())) || 0])
        .range([innerHeight, 0])

      const g = svg
        .append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`)

      g.selectAll(".bar")
        .data(Array.from(data.entries()))
        .enter()
        .append("rect")
        .attr("class", "bar")
        .attr("x", ([feature, _count]) => x(feature) || 0)
        .attr("y", ([_feature, count]) => y(count))
        .attr("width", x.bandwidth())
        .attr("height", ([_feature, count]) => innerHeight - y(count))
        .attr("fill", TYCHE_COLOR.PRIMARY)
        .on("mouseover", function (event, d) {
          showTooltip(event, d)
        })
        .on("mousemove", moveTooltip)
        .on("mouseleave", hideTooltip)

      g.append("g")
        .attr("transform", `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x))
        .selectAll("text")
        .attr("transform", "rotate(-45)")
        .style("text-anchor", "end")

      g.append("g").call(
        d3
          .axisLeft(y)
          .ticks(7)
          .tickFormat(d => Math.round(Number(d)).toString()),
      )

      g.append("text")
        .attr("transform", "rotate(-90)")
        .attr("y", -30)
        .attr("x", -innerHeight / 2)
        .attr("text-anchor", "middle")
        .text("Count")
        .style("font-size", "12px")
    }

    return () => {
      d3.select(".tyche-tooltip").remove()
    }
  }, [observations])

  if (observations.length === 0) {
    return <div className="tyche__mosaic__title">No samples</div>
  }

  return (
    <div>
      <div className="tyche__nominal__feature">{feature}</div>
      <div ref={parentRef} className="tyche__nominal__chart">
        <svg ref={svgRef} style={{ width: "100%" }}></svg>
      </div>
    </div>
  )
}
