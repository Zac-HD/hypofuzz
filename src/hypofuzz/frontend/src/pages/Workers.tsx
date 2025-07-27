import { OrderedSet } from "immutable"
import React, { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { RangeSlider } from "src/components/RangeSlider"
import { useData } from "src/context/DataProvider"
import { formatTime } from "src/utils/testStats"
import { useTooltip } from "src/utils/tooltip"
import { navigateOnClick, readableNodeid } from "src/utils/utils"

interface Segment {
  nodeid: string
  start: number
  end: number
}

interface WorkerReport {
  timestamp_monotonic: number
  nodeid: string
}

class Worker {
  constructor(
    public uuid: string,
    public segments: Segment[],
  ) {}

  visibleSegments(range: [number, number]): Segment[] {
    return this.segments.filter(
      segment => segment.end >= range[0] && segment.start <= range[1],
    )
  }
}

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleString()
}

// 24 hours
const DEFAULT_RANGE_DURATION = 24 * 60 * 60

function niceDefaultRange(
  minTimestamp: number,
  maxTimestamp: number,
): [number, number] {
  // by default: show from maxTimestamp at the end, to DEFAULT_RANGE_DURATION seconds before
  // that at the start.
  return [Math.max(minTimestamp, maxTimestamp - DEFAULT_RANGE_DURATION), maxTimestamp]
}

function nodeColor(nodeid: string): string {
  let hash = 0
  for (let i = 0; i < nodeid.length; i++) {
    hash = ((hash << 5) - hash + nodeid.charCodeAt(i)) & 0xffffffff
  }

  const hue = Math.abs(hash) % 360
  const saturation = 45 + (Math.abs(hash >> 8) % 30) // 45-75%
  const lightness = 45 + (Math.abs(hash >> 16) % 20) // 45-65%

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

function DetailsItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="workers__worker__details__item">
      <span className="workers__worker__details__label">{label}</span>
      <span className="workers__worker__details__value">{value}</span>
    </div>
  )
}

const WorkerBar = ({
  worker,
  range,
  expandedWorkers,
  onWorkerClick,
  segmentStyle,
  navigate,
  showTooltip,
  hideTooltip,
  moveTooltip,
}: {
  worker: Worker
  range: [number, number]
  expandedWorkers: Set<string>
  onWorkerClick: (uuid: string) => void
  segmentStyle: (segment: Segment) => React.CSSProperties
  navigate: ReturnType<typeof useNavigate>
  showTooltip: (text: string, x: number, y: number, id: string) => void
  hideTooltip: (id: string) => void
  moveTooltip: (x: number, y: number, id: string) => void
}) => {
  return (
    <div
      key={worker.uuid}
      className={`workers__worker ${expandedWorkers.has(worker.uuid) ? "workers__worker--expanded" : ""}`}
      onClick={() => onWorkerClick(worker.uuid)}
      // these extra onMouseLeave calls shouldn't be necessary, but I've had trouble
      // with the workers__timeline__segment mouse leave handler not firing consistently
      onMouseLeave={() => hideTooltip("workers")}
    >
      <div className="workers__worker__bar" onMouseLeave={() => hideTooltip("workers")}>
        {worker.visibleSegments(range).map((segment, index) => (
          <div
            key={index}
            className="workers__timeline__segment"
            style={segmentStyle(segment)}
            onClick={event => {
              navigateOnClick(
                event,
                `/tests/${encodeURIComponent(segment.nodeid)}`,
                navigate,
              )
              // prevent the worker click handler from firing (which would distractingly
              // expand the worker details for this worker during navigation)
              event.stopPropagation()
            }}
            onMouseEnter={event =>
              showTooltip(
                readableNodeid(segment.nodeid),
                event.clientX,
                event.clientY,
                "workers",
              )
            }
            onMouseLeave={() => hideTooltip("workers")}
            onMouseMove={event => moveTooltip(event.clientX, event.clientY, "workers")}
          />
        ))}
      </div>
      {expandedWorkers.has(worker.uuid) && <WorkerDetails worker={worker} />}
    </div>
  )
}

const WorkerDetails = ({ worker }: { worker: Worker }) => {
  return (
    <div className="workers__worker__details">
      <div className="workers__worker__details__grid">
        <DetailsItem label="Worker UUID" value={worker.uuid} />
        <DetailsItem
          label="Lifetime"
          value={formatTime(
            worker.segments[worker.segments.length - 1].end - worker.segments[0].start,
          )}
        />
        <DetailsItem
          label="Started"
          value={formatTimestamp(worker.segments[0].start)}
        />
        <DetailsItem
          label="Last seen"
          value={formatTimestamp(worker.segments[worker.segments.length - 1].end)}
        />
      </div>
    </div>
  )
}

export function WorkersPage() {
  const { tests } = useData()
  const navigate = useNavigate()
  const { showTooltip, hideTooltip, moveTooltip } = useTooltip()
  const [expandedWorkers, setExpandedWorkers] = useState<Set<string>>(new Set())

  const workerUuids = OrderedSet(
    Array.from(tests.values())
      .map(test => Array.from(test.reports_by_worker.keys()))
      .flat()
      .sortKey(uuid => uuid),
  )

  const workerReports = new Map<string, WorkerReport[]>()
  workerUuids.forEach(uuid => {
    const allReports: WorkerReport[] = []
    workerReports.set(uuid, allReports)
    Array.from(tests.values()).forEach(test => {
      if (!test.reports_by_worker.has(uuid)) {
        return
      }

      const reports = test.reports_by_worker.get(uuid)!
      allReports.push(
        ...reports.map(report => ({
          timestamp_monotonic: report.timestamp_monotonic!,
          nodeid: test.nodeid,
        })),
      )
    })

    allReports.sortKey(report => report.timestamp_monotonic)
  })

  let minTimestamp: number = Infinity
  let maxTimestamp: number = -Infinity

  let workers: Worker[] = []
  workerUuids.forEach(uuid => {
    const reports = workerReports.get(uuid)!
    const segments: Segment[] = []
    let currentSegment: Segment | null = null

    reports.forEach((report, index) => {
      minTimestamp = Math.min(minTimestamp, report.timestamp_monotonic)
      maxTimestamp = Math.max(maxTimestamp, report.timestamp_monotonic)

      if (!currentSegment || currentSegment.nodeid !== report.nodeid) {
        // flush the current segment
        if (currentSegment) {
          segments.push(currentSegment)
        }
        currentSegment = {
          nodeid: report.nodeid,
          start: report.timestamp_monotonic,
          end: report.timestamp_monotonic,
        }
      } else {
        // extend the current segment
        currentSegment.end = report.timestamp_monotonic
      }

      // if this is the last report, flush the segment
      if (index === reports.length - 1 && currentSegment) {
        segments.push(currentSegment)
      }
    })

    workers.push(new Worker(uuid, segments))
  })

  workers.sortKey(worker => worker.segments[0].start)

  const [visibleRange, setVisibleRange] = useState<[number, number]>(
    niceDefaultRange(minTimestamp, maxTimestamp),
  )

  useEffect(() => {
    setVisibleRange(niceDefaultRange(minTimestamp, maxTimestamp))
  }, [minTimestamp, maxTimestamp])

  const [visibleMin, visibleMax] = visibleRange
  const visibleDuration = visibleMax - visibleMin

  const segmentStyle = (segment: Segment) => {
    let left: number
    let width: number
    if (visibleDuration === 0) {
      left = 0
      width = 100
    } else {
      left = ((segment.start - visibleMin) / visibleDuration) * 100
      width = ((segment.end - segment.start) / visibleDuration) * 100
    }

    return {
      left: `${left}%`,
      width: `${width}%`,
      backgroundColor: nodeColor(segment.nodeid),
    }
  }

  const onWorkerClick = (uuid: string) => {
    setExpandedWorkers(prev => {
      const newSet = new Set(prev)
      if (newSet.has(uuid)) {
        newSet.delete(uuid)
      } else {
        newSet.add(uuid)
      }
      return newSet
    })
  }

  return (
    <div className="card">
      <div className="card__header">Workers </div>
      <div className="card__body">
        <div className="card__text">
          <div className="card__text__paragraph">
            This page shows the history of your workers, and what tests they have been
            fuzzing.
          </div>
          <div className="card__text__paragraph">
            Roughly speaking, "one worker" = "one CPU core".
          </div>
        </div>
        <div className="workers">
          <div className="workers__controls">
            <RangeSlider
              min={minTimestamp}
              max={maxTimestamp}
              value={visibleRange}
              onChange={newRange => setVisibleRange(newRange)}
              step={(maxTimestamp - minTimestamp) / 1000}
            />
          </div>
          <div className="workers__timeline-header">
            <span className="workers__timeline-header__label">
              {formatTimestamp(visibleMin)}
            </span>
            <span className="workers__timeline-header__label">
              {formatTimestamp(visibleMax)}
            </span>
          </div>
          {workers.map(
            worker =>
              worker.visibleSegments(visibleRange).length > 0 && (
                <WorkerBar
                  key={worker.uuid}
                  worker={worker}
                  range={visibleRange}
                  expandedWorkers={expandedWorkers}
                  onWorkerClick={onWorkerClick}
                  segmentStyle={segmentStyle}
                  navigate={navigate}
                  showTooltip={showTooltip}
                  hideTooltip={hideTooltip}
                  moveTooltip={moveTooltip}
                />
              ),
          )}
        </div>
      </div>
    </div>
  )
}
