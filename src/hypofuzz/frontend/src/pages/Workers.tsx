import { OrderedSet } from "immutable"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import { RangeSlider } from "../components/RangeSlider"
import { useData } from "../context/DataProvider"
import { useTooltip } from "../utils/tooltip"
import { navigateOnClick, readableNodeid } from "../utils/utils"

interface Segment {
  nodeid: string
  start: number
  end: number
}

interface WorkerReport {
  timestamp_monotonic: number
  nodeid: string
}

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return date.toLocaleString()
}

function nodeColor(nodeid: string): string {
  let hash = 0
  for (let i = 0; i < nodeid.length; i++) {
    hash = ((hash << 5) - hash + nodeid.charCodeAt(i)) & 0xffffffff
  }

  const hue = Math.abs(hash) % 360
  const saturation = 60 + (Math.abs(hash >> 8) % 30) // 60-90%
  const lightness = 45 + (Math.abs(hash >> 16) % 20) // 45-65%

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

export function WorkersPage() {
  const { tests } = useData()
  const navigate = useNavigate()
  const { showTooltip, hideTooltip, moveTooltip } = useTooltip()

  const workers = OrderedSet(
    Array.from(tests.values())
      .map(test => Array.from(test.reports_by_worker.keys()))
      .flat()
      .sortKey(uuid => uuid),
  )

  const workerReports = new Map<string, WorkerReport[]>()
  workers.forEach(uuid => {
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

  const workerSegments = new Map<string, Segment[]>()
  workers.forEach(uuid => {
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

    workerSegments.set(uuid, segments)
  })

  const [visibleRange, setVisibleRange] = useState<[number, number]>([
    minTimestamp,
    maxTimestamp,
  ])

  useEffect(() => {
    setVisibleRange([minTimestamp, maxTimestamp])
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

  function visibleSegments(segments: Segment[]): Segment[] {
    return segments.filter(
      segment => segment.end >= visibleMin && segment.start <= visibleMax,
    )
  }

  return (
    <div className="card">
      <div className="card__header">Workers</div>
      <div className="card__body">
        <div className="workers">
          <div className="workers__time-controls">
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
          {workers.map(worker => (
            <div key={worker} className="workers__worker">
              {visibleSegments(workerSegments.get(worker) || []).map(
                (segment, index) => {
                  return (
                    <div
                      key={index}
                      className="workers__timeline__segment"
                      style={segmentStyle(segment)}
                      onClick={event =>
                        navigateOnClick(
                          event,
                          `/tests/${encodeURIComponent(segment.nodeid)}`,
                          navigate,
                        )
                      }
                      onMouseEnter={event => {
                        showTooltip(
                          readableNodeid(segment.nodeid),
                          event.clientX,
                          event.clientY,
                          "workers",
                        )
                      }}
                      onMouseLeave={() => {
                        hideTooltip("workers")
                      }}
                      onMouseMove={event => {
                        moveTooltip(event.clientX, event.clientY, "workers")
                      }}
                    ></div>
                  )
                },
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
