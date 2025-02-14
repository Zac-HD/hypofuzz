import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { TestRecord } from '../types/dashboard';
import { Link } from 'react-router-dom';
import { Toggle } from './Toggle';
import { usePreference } from '../hooks/usePreference';

interface Props {
  data: TestRecord[];
}

export function CoverageProgress({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [isLog, setIsLog] = usePreference<boolean>('graph_scale', false);
  const [showTime, setShowTime] = usePreference<boolean>('graph_x_axis', false);

  useEffect(() => {
    if (!data.length || !svgRef.current) return;

    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 30, bottom: 30, left: 60 };
    const width = svgRef.current.clientWidth - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const svg = d3.select(svgRef.current)
      .attr('width', width + margin.left + margin.right)
      .attr('height', height + margin.top + margin.bottom)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    const x = isLog
      ? d3.scaleLog()
          .domain([1, d3.max(data, d => showTime ? d.elapsed_time : d.ninputs) || 1])
          .range([0, width])
      : d3.scaleLinear()
          .domain([0, d3.max(data, d => showTime ? d.elapsed_time : d.ninputs) || 0])
          .range([0, width]);

    const y = d3.scaleLinear()
      .domain([0, d3.max(data, d => d.branches) || 0])
      .nice()
      .range([height, 0]);

    const line = d3.line<typeof data[0]>()
      .x(d => x(Math.max(1, showTime ? d.elapsed_time : d.ninputs)))
      .y(d => y(d.branches));

    svg.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x)
        .ticks(5)
        .tickFormat(d => d3.format(",")(d as number)));

    svg.append('g')
      .call(d3.axisLeft(y));

    svg.append('path')
      .datum(data)
      .attr('fill', 'none')
      .attr('stroke', 'rgb(75, 192, 192)')
      .attr('stroke-width', 1.5)
      .attr('d', line);

    svg.selectAll('circle')
      .data(data)
      .join('circle')
      .attr('cx', d => x(Math.max(1, showTime ? d.elapsed_time : d.ninputs)))
      .attr('cy', d => y(d.branches))
      .attr('r', 3)
      .attr('fill', 'rgb(75, 192, 192)');

    svg.append('text')
      .attr('x', width / 2)
      .attr('y', height + margin.bottom)
      .style('text-anchor', 'middle')
      .text(showTime ? 'Time (s)' : 'Inputs');

  }, [data, isLog, showTime]);

  let lastResult = data[data.length - 1]

  return (
    <div className="coverage-progress">
      <div className="coverage-progress__header">
        <h2>Coverage</h2>
        <div className="coverage-progress__controls">
          <Toggle
            value={showTime}
            onChange={setShowTime}
            options={[
              { value: false, label: 'Inputs' },
              { value: true, label: 'Time' }
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
