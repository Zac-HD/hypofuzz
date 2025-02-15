import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { TestRecord } from '../types/dashboard';
import { Toggle } from './Toggle';
import { usePreference } from '../hooks/usePreference';

interface Props {
  data: Record<string, TestRecord[]>;
}


// in pixels
const distanceThreshold = 15;

export function CoverageGraph({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [isLog, setIsLog] = usePreference<boolean>('graph_scale', false);
  const [axisOption, setAxisOption] = usePreference<string>('graph_x_axis', "time");

  function xValue(d: TestRecord) {
    return axisOption == "time" ? d.elapsed_time : d.ninputs
  }

  useEffect(() => {
    if (!svgRef.current || Object.keys(data).length === 0) {
      return;
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const tooltip = d3.select('.aggregate-graph')
      .append('div')
      .attr('class', 'aggregate-graph__tooltip');

    const margin = { top: 20, right: 150, bottom: 30, left: 60 };
    // const margin = { top: 0, right: 0, bottom: 0, left: 0 };

    const width = svgRef.current.clientWidth - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create color scale
    const nodeIds = Array.from(Object.keys(data));
    const color = d3.scaleOrdinal(d3.schemeCategory10).domain(nodeIds);
    const latests = Object.entries(data).map(([nodeid, points]) => points[points.length - 1])

    const x = isLog
      ? d3.scaleLog()
          .domain([1, d3.max(latests, d => xValue(d)) || 1])
          .range([0, width])
      : d3.scaleLinear()
          .domain([0, d3.max(latests, d => xValue(d)) || 0])
          .range([0, width]);

    const y = d3.scaleLinear()
      .domain([0, d3.max(latests, d => d.branches) || 0])
      .range([height, 0]);

    const line = d3.line<TestRecord>()
      .x(d => x(Math.max(1, xValue(d))))
      .y(d => y(d.branches));


    g.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', 'none')
      .attr('pointer-events', 'all')
      .on('mousemove', function(event) {
        const [mouseX, mouseY] = d3.pointer(event);

        // https://stackoverflow.com/a/71632002
        let closestPoint = null as TestRecord | null;
        let closestDistance = Infinity;

        Object.values(data).forEach(points => {
          if (!points || points.length === 0) return;

          const sortedPoints = points.sort((a, b) => xValue(a) - xValue(b));

          sortedPoints.forEach(point => {
            const distance = Math.sqrt((x(xValue(point)) - mouseX) ** 2 + (y(point.branches) - mouseY) ** 2);

            if (distance < closestDistance && distance < distanceThreshold) {
              closestDistance = distance;
              closestPoint = point;
            }
          });
        });

        if (closestPoint) {
          // Reset all lines
          g.selectAll('path').classed('coverage-line__selected', false);

          g.selectAll<SVGPathElement, TestRecord[]>('path')
            .filter(points => Array.isArray(points) && points.length > 0 && points[0].nodeid === closestPoint!.nodeid)
            .classed('coverage-line__selected', true);

          tooltip
            .style('display', 'block')
            .style('left', `${event.pageX + 10}px`)
            .style('top', `${event.pageY - 10}px`)
            .html(`
              <strong>${closestPoint.nodeid.split('::').pop() || closestPoint.nodeid}</strong><br/>
              ${closestPoint.branches.toLocaleString()} branches
              (@ ${xValue(closestPoint).toLocaleString()} ${axisOption == "time" ? "seconds" : "inputs"})
            `);
        } else {
          tooltip.style('display', 'none');
        }
      })
      .on('mouseleave', function() {
        // Reset all lines
        g.selectAll('path').attr('coverage-line__selected', false);
        tooltip.style('display', 'none');
      });


    // draw a line for each test
    Object.entries(data).forEach(([nodeid, points]) => {
      g.append('path')
        .datum(points)
        .attr('fill', 'none')
        .attr('stroke', color(nodeid))
        .attr('d', line)
        .attr('class', 'coverage-line')
        .style('cursor', 'pointer')
        .on('mouseover', function() {
          d3.select(this).classed('coverage-line__selected', true);

          // also select corresponding legend item
          legend.selectAll('g')
            .filter(d => d === nodeid)
            .style('font-weight', 'bold');
        })
        .on('mouseout', function() {
          d3.select(this).classed('coverage-line__selected', false);

          // also deselect corresponding legend item
          legend.selectAll('g').style('font-weight', 'normal');
        })
        .on('click', () => {
          window.location.href = `/tests/${encodeURIComponent(nodeid)}`;
        });
    });

    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x)
        .ticks(5)
        .tickFormat(d => d.toLocaleString()));

    g.append('g')
      .call(d3.axisLeft(y)
        .ticks(5));

    g.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('y', 0 - margin.left)
      .attr('x', 0 - (height / 2))
      .attr('dy', '1em')
      .style('text-anchor', 'middle')
      .text('Branches');

    g.append('text')
      .attr('x', width / 2)
      .attr('y', height + margin.bottom)
      .style('text-anchor', 'middle')
      .text(axisOption == "time" ? 'Time (s)' : 'Inputs');

    const legend = g.append('g').attr('transform', `translate(${width + 10},0)`);

    nodeIds.forEach((nodeid, i) => {
      const legendItem = legend.append('g')
        .attr('transform', `translate(0,${i * 20})`)
        .style('cursor', 'pointer')
        .on('mouseover', function() {
          // Highlight corresponding line
          g.selectAll<SVGPathElement, TestRecord[]>('path')
            .filter(d => Array.isArray(d) && d.length > 0 && d[0].nodeid === nodeid)
            .classed('coverage-line__selected', true);

          d3.select(this).style('font-weight', 'bold');
        })
        .on('mouseout', function() {
          // Reset line
          g.selectAll('path').classed('coverage-line__selected', false);
          d3.select(this).style('font-weight', 'normal');
        })
        .on('click', () => {
          window.location.href = `/tests/${encodeURIComponent(nodeid)}`;
        });

      legendItem.append('line')
        .attr('x1', 0)
        .attr('x2', 20)
        .attr('y1', 10)
        .attr('y2', 10)
        .attr('stroke', color(nodeid))

      legendItem.append('text')
        .attr('x', 25)
        .attr('y', 15)
        .text(nodeid.split('::').pop() || nodeid)
        .style('font-size', '12px');
    });

  }, [data, isLog, axisOption]);

  return (
    <div className="aggregate-graph">
      <div className="aggregate-graph__header">
        <h2>Coverage</h2>
        <div className="aggregate-graph__controls">
          <Toggle
            value={axisOption}
            onChange={setAxisOption}
            options={[
              { value: "inputs", label: 'Inputs' },
              { value: "time", label: 'Time' }
            ]}
          />
          <Toggle
            value={isLog}
            onChange={setIsLog}
            options={[
              { value: false, label: 'Linear' },
              { value: true, label: 'Log' }
            ]}
          />
        </div>
      </div>
      <svg ref={svgRef} style={{ width: '100%', height: '300px' }} />
    </div>
  );
}
