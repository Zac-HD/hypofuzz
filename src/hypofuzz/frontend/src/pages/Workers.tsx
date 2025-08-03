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

interface TimePeriod {
  label: string
  // duration in seconds
  duration: number | null
}

const TIME_PERIODS: TimePeriod[] = [
  { label: "Latest", duration: null },
  { label: "1 hour", duration: 1 * 60 * 60 },
  { label: "1 day", duration: 24 * 60 * 60 },
  { label: "7 days", duration: 7 * 24 * 60 * 60 },
  { label: "1 month", duration: 30 * 24 * 60 * 60 },
  { label: "3 months", duration: 90 * 24 * 60 * 60 },
]

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleString()
}

// tolerance for a region, in seconds
const REGION_TOLERANCE = 5 * 60

function segmentRegions(segments: Segment[]): [number, number][] {
  // returns a list of [start, end] regions, where a region is defined as the largest
  // interval where there is no timestamp without an active segment.
  // so in
  //
  // ```
  //  [--]          [-------]
  //   [---]  [-]     [------]
  // [----]   [--]
  // ```
  // there are 3 regions.

  // We iterate over the egments in order of start time. We track the latest seen end time.
  // If we ever see a segment with a later start time than the current end time, that means
  // there must have been empty space between them, which marks a new region.

  // assert segments are sorted by segment.start
  console.assert(
    segments.every(
      (segment, index) => index === 0 || segment.start >= segments[index - 1].start,
    ),
  )

  if (segments.length == 0) {
    return []
  }

  let regions: [number, number][] = []
  let regionStart = segments[0].start
  let latestEnd = segments[0].end
  for (const segment of segments) {
    if (segment.start > latestEnd + REGION_TOLERANCE) {
      // this marks a new region
      regions.push([regionStart, latestEnd])
      regionStart = segment.start
    }

    latestEnd = Math.max(latestEnd, segment.end)
  }

  // finalize the current region
  regions.push([regionStart, latestEnd])
  return regions
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
  const [selectedPeriod, setSelectedPeriod] = useState<TimePeriod>(TIME_PERIODS[0]) // Default to "Latest"
  const [userRange, setUserRange] = useState<[number, number] | null>(null)

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
  const segments = workers
    .flatMap(worker => worker.segments)
    .sortKey(segment => segment.start)
  const regions = segmentRegions(segments)

  const span = maxTimestamp - minTimestamp
  // find the first time period which is larger than the span of the workers.
  // that time period is available, but anything after is not.
  const firstLargerPeriod = TIME_PERIODS.findIndex(
    period => period.duration !== null && period.duration >= span,
  )

  function getSliderRange(): [number, number] {
    if (selectedPeriod.duration === null) {
      const latestRegion = regions[regions.length - 1]
      // the range is just the last region, unless there are no segments, in which case
      // we use the min/max timestamp
      return regions.length > 0
        ? [latestRegion[0], latestRegion[1]]
        : [minTimestamp, maxTimestamp]
    }

    const range: [number, number] = [
      Math.max(minTimestamp, maxTimestamp - selectedPeriod.duration!),
      maxTimestamp,
    ]

    // trim the slider range to remove any time at the beginning or end when there
    // are no active workers
    let trimmedMin: number | null = null
    let trimmedMax: number | null = null
    for (const worker of workers) {
      const visibleSegments = worker.visibleSegments(range)
      if (visibleSegments.length === 0) {
        continue
      }

      if (trimmedMin === null || visibleSegments[0].start < trimmedMin) {
        trimmedMin = visibleSegments[0].start
      }

      if (
        trimmedMax === null ||
        visibleSegments[visibleSegments.length - 1].end > trimmedMax
      ) {
        trimmedMax = visibleSegments[visibleSegments.length - 1].end
      }
    }

    return [trimmedMin ?? range[0], trimmedMax ?? range[1]]
  }
  const sliderRange = getSliderRange()
  const visibleRange = userRange ?? sliderRange

  useEffect(() => {
    // reset the range when clicking on a period, even if it's the same period. This gives a
    // nice "reset button" ux to users.
    setUserRange(null)
  }, [selectedPeriod])

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

    // TODO we should compute a min in pixels, not percentage.
    width = Math.max(width, 0.1)

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
            <div className="workers__durations">
              {TIME_PERIODS.map((period, index) => {
                const available = index <= firstLargerPeriod
                return (
                  <div
                    key={index}
                    className={`workers__durations__button ${
                      selectedPeriod.label === period.label
                        ? "workers__durations__button--active"
                        : ""
                    } ${!available ? "workers__durations__button--disabled" : ""}`}
                    onClick={() => available && setSelectedPeriod(period)}
                  >
                    {period.label}
                  </div>
                )
              })}
            </div>
            <RangeSlider
              min={sliderRange[0]}
              max={sliderRange[1]}
              value={visibleRange}
              onChange={newRange => setUserRange(newRange)}
              step={(sliderRange[1] - sliderRange[0]) / 1000}
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
