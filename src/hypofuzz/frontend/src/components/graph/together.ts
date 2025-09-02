import { Report } from "src/types/dashboard"

import { GraphReport } from "./types"

// returns workerid: [workerid], mapping each worker to a list of workers that
// overlapped it at any point
function workerOverlaps(reportsByWorker: Map<string, Report[]>): Map<string, string[]> {
  const intervals = new Map<string, { start: number; end: number }>()
  for (const [workerUuid, workerReports] of reportsByWorker.entries()) {
    if (workerReports.length === 0) {
      continue
    }
    intervals.set(workerUuid, {
      start: workerReports[0].timestamp_monotonic!,
      end: workerReports[workerReports.length - 1].timestamp_monotonic!,
    })
  }

  const workerIds = Array.from(intervals.keys())
  const overlaps = new Map<string, string[]>()

  for (const id of workerIds) {
    overlaps.set(id, [])
  }

  for (let i = 0; i < workerIds.length; i++) {
    const aId = workerIds[i]
    const a = intervals.get(aId)!
    for (let j = i + 1; j < workerIds.length; j++) {
      const bId = workerIds[j]
      const b = intervals.get(bId)!
      if (a.start <= b.end && b.start <= a.end) {
        overlaps.get(aId)!.push(bId)
        overlaps.get(bId)!.push(aId)
      }
    }
  }

  return overlaps
}

// - compute a map of workers: [overlapping_workers], mapping each worker to a list of
//   workers which ever overlapped with it
// - for each report1, report2 in zip(reports, reports[1:]), if report2 decreases from
//   report1 in either fingerprints or behaviors, and the worker of report2 is concurrent
//   with the worker of report1, then filter out report2 from the list of reports.
export function togetherReports(
  reportsByWorker: Map<string, Report[]>,
  reports: GraphReport[],
): GraphReport[] {
  if (reports.length <= 1) {
    return reports
  }

  const overlaps = workerOverlaps(reportsByWorker)
  const result: GraphReport[] = []
  result.push(reports[0])
  let mostRecentVisible = reports[0]
  for (let i = 1; i < reports.length; i++) {
    const r1 = mostRecentVisible
    const r2 = reports[i]
    const w1 = mostRecentVisible.worker_uuid
    const w2 = r2.worker_uuid

    const decreases = r2.behaviors < r1.behaviors || r2.fingerprints < r1.fingerprints
    if (decreases && overlaps.get(w1)!.includes(w2)) {
      continue
    }
    mostRecentVisible = r2
    result.push(r2)
  }

  return result
}
