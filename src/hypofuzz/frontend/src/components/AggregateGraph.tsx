import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { TestRecord } from '../types/dashboard';
import { Toggle } from './Toggle';
import { usePreference } from '../hooks/usePreference';

interface Props {
  data: Record<string, TestRecord[]>;
}

interface DataPoint {
  testId: string;
  inputs: number;
  branches: number;
  elapsed_time: number;
}

function processData(data: Record<string, TestRecord[]>): DataPoint[] {
  const points: DataPoint[] = [];

  Object.entries(data).forEach(([testId, records]) => {
    records.forEach(record => {
      points.push({
        testId,
        inputs: record.ninputs,
        branches: record.branches,
        elapsed_time: record.elapsed_time,
      });
    });
  });

  return points;
}

export function AggregateGraph({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [isLog, setIsLog] = usePreference<boolean>('graph_scale', false);
  const [showTime, setShowTime] = usePreference<boolean>('graph_x_axis', false);

  useEffect(() => {
    if (!svgRef.current) return;

    const processedData = processData(data);
    if (processedData.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 20, right: 150, bottom: 30, left: 60 };
    const width = svgRef.current.clientWidth - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create color scale
    const testIds = Array.from(new Set(processedData.map(d => d.testId)));
    const color = d3.scaleOrdinal(d3.schemeCategory10).domain(testIds);

    // X scale (inputs or time)
    const x = isLog
      ? d3.scaleLog()
          .domain([1, d3.max(processedData, d => showTime ? d.elapsed_time : d.inputs) || 1])
          .range([0, width])
      : d3.scaleLinear()
          .domain([0, d3.max(processedData, d => showTime ? d.elapsed_time : d.inputs) || 0])
          .range([0, width]);

    // Y scale (branches)
    const y = d3.scaleLinear()
      .domain([0, d3.max(processedData, d => d.branches) || 0])
      .range([height, 0]);

    // Line generator
    const line = d3.line<DataPoint>()
      .x(d => x(Math.max(1, showTime ? d.elapsed_time : d.inputs)))
      .y(d => y(d.branches));

    // Group data by testId
    const groupedData = d3.group(processedData, d => d.testId);

    // Add lines for each test
    groupedData.forEach((points, testId) => {
      const sortedPoints = points.sort((a, b) => a.inputs - b.inputs);

      const path = g.append('path')
        .datum(sortedPoints)
        .attr('fill', 'none')
        .attr('stroke', color(testId))
        .attr('stroke-width', 2)
        .attr('d', line)
        .attr('class', 'coverage-line')
        .style('cursor', 'pointer')
        .on('mouseover', function() {
          d3.select(this)
            .attr('stroke-width', 4);

          // Highlight legend item
          legend.selectAll('g')
            .filter(d => d === testId)
            .style('font-weight', 'bold');
        })
        .on('mouseout', function() {
          d3.select(this)
            .attr('stroke-width', 2);

          // Reset legend item
          legend.selectAll('g')
            .style('font-weight', 'normal');
        })
        .on('click', () => {
          window.location.href = `/test/${encodeURIComponent(testId)}`;
        });
    });

    // Add axes
    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(x)
        .ticks(5)
        .tickFormat(d => d.toLocaleString()));

    g.append('g')
      .call(d3.axisLeft(y)
        .ticks(5));

    // Add labels
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
      .text(showTime ? 'Time (s)' : 'Inputs');

    // Add legend with hover effects
    const legend = g.append('g')
      .attr('transform', `translate(${width + 10},0)`);

    testIds.forEach((testId, i) => {
      const legendItem = legend.append('g')
        .attr('transform', `translate(0,${i * 20})`)
        .style('cursor', 'pointer')
        .on('mouseover', function() {
          // Highlight corresponding line
          g.selectAll<SVGPathElement, DataPoint[]>('path')
            .filter(d => {
              if (!Array.isArray(d)) return false;
              return d.length > 0 && d[0].testId === testId;
            })
            .attr('stroke-width', 4);

          d3.select(this)
            .style('font-weight', 'bold');
        })
        .on('mouseout', function() {
          // Reset line
          g.selectAll('path')
            .attr('stroke-width', 2);

          d3.select(this)
            .style('font-weight', 'normal');
        })
        .on('click', () => {
          window.location.href = `/test/${encodeURIComponent(testId)}`;
        });

      legendItem.append('line')
        .attr('x1', 0)
        .attr('x2', 20)
        .attr('y1', 10)
        .attr('y2', 10)
        .attr('stroke', color(testId))
        .attr('stroke-width', 2);

      legendItem.append('text')
        .attr('x', 25)
        .attr('y', 15)
        .text(testId.split('::').pop() || testId)
        .style('font-size', '12px');
    });

  }, [data, isLog, showTime]);

  return (
    <div className="aggregate-graph">
      <div className="aggregate-graph__header">
        <h2>Coverage</h2>
        <div className="aggregate-graph__controls">
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
