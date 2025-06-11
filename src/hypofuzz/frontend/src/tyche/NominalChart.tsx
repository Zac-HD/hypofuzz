import { axisBottom as d3_axisBottom, axisLeft as d3_axisLeft } from "d3-axis"
import {
  scaleBand as d3_scaleBand,
  scaleLinear as d3_scaleLinear,
  scaleOrdinal as d3_scaleOrdinal,
} from "d3-scale"
import { select as d3_select } from "d3-selection"
import { Set } from "immutable"
import { useEffect, useMemo, useRef } from "react"

import { Observation } from "../types/dashboard"
import { useTooltip } from "../utils/tooltip"
import { max, sum } from "../utils/utils"
import { Filter, useFilters } from "./FilterContext"
import { TYCHE_COLOR } from "./Tyche"
import { NOT_PRESENT_STRING, PRESENT_STRING } from "./Tyche"

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
  observations: { raw: Observation[]; filtered: Observation[] }
}

const HORIZONTAL_BAR_FEATURE_CUTOFF = 5

const SELECTION_STROKE_WIDTH = 2.5

export function NominalChart({ feature, observations }: NominalChartProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const { filters, setFilters } = useFilters()
  const { showTooltip, hideTooltip, moveTooltip } = useTooltip()
  const nominalFilters = filters.get(feature) || []

  const selectedValues = useMemo(() => {
    if (nominalFilters.length === 0) {
      return Set<string>()
    }

    console.assert(nominalFilters.length === 1)
    const filter = nominalFilters[0]
    return Set(filter.extraData.selectedValues)
  }, [nominalFilters])

  observations = {
    raw: observations.raw.filter(obs => obs.status !== "gave_up"),
    filtered: observations.filtered.filter(obs => obs.status !== "gave_up"),
  }

  const onValueClick = (value: string) => {
    let newSelection = Set<string>()

    // If clicking the same value that's already selected alone, deselect it
    if (selectedValues.equals(Set([value]))) {
      newSelection = Set()
    } else {
      // Otherwise, select just this value
      newSelection = Set([value])
    }

    let name
    if (newSelection.size === 1) {
      name = newSelection.first()!
    } else {
      name = newSelection.map(value => `${value}`).join(" or ")
    }

    const nominalFilters = []
    if (newSelection.size > 0) {
      nominalFilters.push(
        new Filter(
          name,
          (obs: Observation) => {
            return newSelection.some(value => {
              return obs.features.get(feature) === value
            })
          },
          feature,
          {
            selectedValues: newSelection,
          },
        ),
      )
    }

    const newFilters = new Map(filters)
    newFilters.set(feature, nominalFilters)
    setFilters(newFilters)
  }

  useEffect(() => {
    const distinctRawValues = Set<string>(
      observations.raw.map(obs => obs.features.get(feature)),
    )
    // value: count
    let data = new Map<string, number>()

    for (const observation of observations.filtered) {
      const value = observation.features.get(feature)
      data.set(value, (data.get(value) || 0) + 1)
    }
    const total = sum(Array.from(data.values()))

    data = new Map(
      [...data.entries()].sortKey(([value, _count]) => {
        if (value === PRESENT_STRING) return 0
        if (value === NOT_PRESENT_STRING) return 1
        return value
      }),
    )

    d3.select(svgRef.current).selectAll("*").remove()

    const width = parentRef.current!.clientWidth
    const height = distinctRawValues.size < HORIZONTAL_BAR_FEATURE_CUTOFF ? 85 : 170

    const svg = d3
      .select(svgRef.current)
      .attr("width", width)
      .attr("height", height)
      .append("g")

    const showTooltipHandler = function (event: MouseEvent, d: [string, number]) {
      const [label, count] = d
      showTooltip(`${feature}<br>${label}: ${count}`, event.clientX, event.clientY)
    }

    // use a horizontally-stacked bar chart for 1-4 different feature labels,
    // and a standard histogram otherwise.
    //
    // use the number of distinct values in the unfiltered observations, so we
    // don't change up the display type on the user when they're drilling down.
    if (distinctRawValues.size < HORIZONTAL_BAR_FEATURE_CUTOFF) {
      const margin = { top: 0, right: 15, bottom: 20, left: 15 }
      const innerWidth = width - margin.left - margin.right
      const innerHeight = height - margin.top - margin.bottom

      const x = d3.scaleLinear().domain([0, 1]).range([0, innerWidth])

      let colorScale: (feature: string) => string
      if (data.has(PRESENT_STRING) || data.has(NOT_PRESENT_STRING)) {
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

      data.forEach((count, value) => {
        const barWidth = (count / total) * innerWidth
        const isSelected = selectedValues.has(value)

        // outer rect
        g.append("rect")
          .attr("x", xAccumulator)
          .attr("y", 0)
          .attr("width", barWidth)
          .attr("height", barHeight)
          .attr("fill", colorScale(value))
          .style("cursor", "pointer")
          .on("click", () => onValueClick(value))
          .on("mouseover", event => {
            showTooltipHandler(event, [value, count])
          })
          .on("mousemove", event => moveTooltip(event.clientX, event.clientY))
          .on("mouseleave", hideTooltip)

        // inner rect (for inset white border when selected)
        if (isSelected) {
          g.append("rect")
            .attr("x", xAccumulator + SELECTION_STROKE_WIDTH)
            .attr("y", SELECTION_STROKE_WIDTH)
            .attr("width", barWidth - 2 * SELECTION_STROKE_WIDTH)
            .attr("height", barHeight - 2 * SELECTION_STROKE_WIDTH)
            .attr("fill", colorScale(value))
            .attr("stroke", "white")
            .attr("stroke-width", SELECTION_STROKE_WIDTH)
            .style("pointer-events", "none") // let outer rect handle all of the clicks
        }

        g.append("text")
          .attr("x", xAccumulator + barWidth / 2)
          .attr("y", barHeight / 2)
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("fill", "white")
          .text(value)
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
        .attr("x", ([value, _count]) => x(value) || 0)
        .attr("y", ([_value, count]) => y(count))
        .attr("width", x.bandwidth())
        .attr("height", ([_value, count]) => innerHeight - y(count))
        .attr("fill", TYCHE_COLOR.PRIMARY)
        .style("cursor", "pointer")
        .on("click", function (event, [value, _count]) {
          onValueClick(value)
        })
        .on("mouseover", function (event, d) {
          showTooltipHandler(event, d)
        })
        .on("mousemove", event => moveTooltip(event.clientX, event.clientY))
        .on("mouseleave", hideTooltip)

      g.selectAll(".inner-bar")
        .data(
          Array.from(data.entries()).filter(([value, _count]) =>
            selectedValues.has(value),
          ),
        )
        .enter()
        .append("rect")
        .attr("class", "inner-bar")
        .attr("x", ([value, _count]) => (x(value) || 0) + SELECTION_STROKE_WIDTH)
        .attr("y", ([_value, count]) => y(count) + SELECTION_STROKE_WIDTH)
        .attr("width", x.bandwidth() - 2 * SELECTION_STROKE_WIDTH)
        .attr(
          "height",
          ([_value, count]) => innerHeight - y(count) - 2 * SELECTION_STROKE_WIDTH,
        )
        .attr("fill", TYCHE_COLOR.PRIMARY)
        .attr("stroke", "white")
        .attr("stroke-width", SELECTION_STROKE_WIDTH)
        .style("pointer-events", "none")

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
      hideTooltip()
    }
  }, [observations, selectedValues, feature, onValueClick])

  return (
    <div>
      <div className="tyche__nominal__feature">{feature}</div>
      <div ref={parentRef} className="tyche__nominal__chart">
        <svg ref={svgRef} style={{ width: "100%" }}></svg>
      </div>
    </div>
  )
}
