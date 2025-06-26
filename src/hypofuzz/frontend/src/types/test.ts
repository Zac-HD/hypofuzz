import {
  Dataclass,
  Failure,
  Observation,
  Phase,
  Report,
  StatusCounts,
  TestStatus,
} from "src/types/dashboard"
import { bisectRight } from "src/utils/utils"

function report_with_diff(report: Report, last_worker_report: Report | null): Report {
  const last_status_counts = last_worker_report
    ? last_worker_report.status_counts
    : new StatusCounts()
  const last_elapsed_time = last_worker_report ? last_worker_report.elapsed_time : 0.0
  const status_counts_diff = report.status_counts.subtract(last_status_counts)
  const elapsed_time_diff = report.elapsed_time - last_elapsed_time
  const timestamp_monotonic = last_worker_report
    ? Math.max(
        report.timestamp,
        last_worker_report.timestamp_monotonic! + elapsed_time_diff,
      )
    : report.timestamp

  console.assert(
    Array.from(status_counts_diff.counts.values()).every(count => count >= 0),
  )
  console.assert(elapsed_time_diff >= 0.0)

  return report.withProperties({
    status_counts_diff: status_counts_diff,
    elapsed_time_diff: elapsed_time_diff,
    timestamp_monotonic: timestamp_monotonic,
  })
}

export class Test extends Dataclass<Test> {
  // if it's been this long since the last report in seconds, consider the test status
  // to be "waiting" instead of "running"
  static WAITING_STATUS_DURATION = 120

  public linear_reports: Report[]
  private _status_counts_cumsum: Map<number, [number, StatusCounts[]]>
  private _elapsed_time_cumsum: Map<number, [number, number[]]>
  // when we finished receiving all data for this worker from the websocket. null if
  // we have not finished receiving data.
  public load_finished_at: number | null = null

  constructor(
    public database_key: string | null,
    public nodeid: string,
    public rolling_observations: Observation[],
    public corpus_observations: Observation[],
    public failures: Map<string, Failure>,
    public reports_by_worker: Map<string, Report[]>,
  ) {
    super()
    this.linear_reports = []
    // TODO we should use an actual LRUCache for memory here, like in python.
    // https://github.com/isaacs/node-lru-cache looks like a good option
    this._status_counts_cumsum = new Map()
    this._elapsed_time_cumsum = new Map()
    this.load_finished_at = null

    const reports_by_worker_ = this.reports_by_worker
    this.reports_by_worker = new Map()

    // TODO: use k-way merge for performance?

    // list of (worker_uuid, report) for each report, sorted by report.timestamp
    const sorted_reports = Array.from(reports_by_worker_.entries())
      .flatMap(([worker_uuid, reports]) => reports.map(report => [worker_uuid, report]))
      .sortKey(([_worker_uuid, report]) => (report as Report).timestamp)
    for (const [worker_uuid, report] of sorted_reports) {
      this.add_report(worker_uuid as string, report as Report)
    }
    this._check_invariants()
  }

  static fromJson(data: any): Test {
    return new Test(
      data.database_key,
      data.nodeid,
      // observations will be updated later by another websocket event
      [],
      [],
      new Map(
        Object.entries(data.failures).map(([key, value]) => [
          key,
          Failure.fromJson(value),
        ]),
      ),
      new Map(
        Object.entries(data.reports_by_worker).map(([key, value]) => [
          key,
          (value as any[]).map(Report.fromJson),
        ]),
      ),
    )
  }

  _assert_reports_ordered(reports: Report[]) {
    for (let i = 0; i < reports.length - 1; i++) {
      console.assert(
        reports[i].timestamp_monotonic! <= reports[i + 1].timestamp_monotonic!,
      )
    }
  }

  _check_invariants() {
    this._assert_reports_ordered(this.linear_reports)

    const linear_status_counts = this.linear_status_counts(null)
    for (let i = 0; i < linear_status_counts.length - 1; i++) {
      console.assert(linear_status_counts[i].sum() <= linear_status_counts[i + 1].sum())
    }
    const linear_elapsed_time = this.linear_elapsed_time(null)
    for (let i = 0; i < linear_elapsed_time.length - 1; i++) {
      console.assert(linear_elapsed_time[i] <= linear_elapsed_time[i + 1])
    }
    console.assert(
      linear_elapsed_time.length === linear_status_counts.length &&
        linear_status_counts.length === this.linear_reports.length,
    )

    for (const [_worker_uuid, reports] of this.reports_by_worker.entries()) {
      this._assert_reports_ordered(reports)
    }
  }

  add_report(worker_uuid: string, report: Report) {
    // This function implements Test.add_report in python. Make sure to keep the
    // two versions in sync.

    let last_report_worker: Report | null = null
    let reports_index = 0
    if (this.reports_by_worker.has(worker_uuid)) {
      const reports = this.reports_by_worker.get(worker_uuid)!
      reports_index = bisectRight(reports, report.elapsed_time, r => r.elapsed_time)
      last_report_worker = reports_index != 0 ? reports[reports_index - 1] : null
    }

    const linear_report = report_with_diff(report, last_report_worker)

    if (!this.reports_by_worker.has(worker_uuid)) {
      this.reports_by_worker.set(worker_uuid, [])
    }
    this.reports_by_worker.get(worker_uuid)!.splice(reports_index, 0, linear_report)

    if (
      linear_report.phase !== Phase.REPLAY ||
      (linear_report.behaviors >= this.behaviors &&
        linear_report.fingerprints >= this.fingerprints)
    ) {
      const index = bisectRight(
        this.linear_reports,
        linear_report.timestamp_monotonic!,
        r => r.timestamp_monotonic,
      )
      this.linear_reports.splice(index, 0, linear_report)
      if (index != this.linear_reports.length - 1) {
        let next_worker_report = null
        let i_offset
        for (
          i_offset = 0;
          i_offset < this.linear_reports.length - (index + 1);
          i_offset++
        ) {
          const report_candidate = this.linear_reports[index + 1 + i_offset]
          if (linear_report.worker_uuid === report_candidate.worker_uuid!) {
            next_worker_report = report_candidate
            break
          }
        }

        if (next_worker_report) {
          console.assert(
            this.linear_reports[index + 1 + i_offset] === next_worker_report,
          )
          this.linear_reports[index + 1 + i_offset] = report_with_diff(
            next_worker_report,
            linear_report,
          )
        }

        for (const cache of [this._status_counts_cumsum, this._elapsed_time_cumsum]) {
          for (const [key, [start_idx, values]] of cache.entries()) {
            if (index >= start_idx) {
              cache.set(key, [start_idx, values.slice(0, index - start_idx) as any[]])
            }
          }
        }
      }
    }
  }

  get status() {
    if (this.failures.size > 0) {
      return TestStatus.FAILED
    }
    if (this.linear_reports.length === 0) {
      return TestStatus.WAITING
    }

    const latest = this.linear_reports[this.linear_reports.length - 1]
    const timestamp = new Date().getTime() / 1000
    if (latest.phase == Phase.SHRINK) {
      return TestStatus.SHRINKING
    }
    if (
      latest.ninputs === 0 ||
      latest.timestamp < timestamp - Test.WAITING_STATUS_DURATION
    ) {
      return TestStatus.WAITING
    }
    return TestStatus.RUNNING
  }

  get behaviors() {
    if (this.linear_reports.length === 0) {
      return 0
    }
    return this.linear_reports[this.linear_reports.length - 1].behaviors
  }

  get fingerprints() {
    if (this.linear_reports.length === 0) {
      return 0
    }
    return this.linear_reports[this.linear_reports.length - 1].fingerprints
  }

  get since_new_behavior() {
    // TODO take linearization into account properly here. I think we want "linearized
    // inputs since branch count last increased". Iterate backwards over linear_status_counts?
    if (this.linear_reports.length === 0) {
      return null
    }
    return this.linear_reports[this.linear_reports.length - 1].since_new_behavior
  }

  elapsed_time(since: number | null): number {
    const elapsed_times = this.linear_elapsed_time(since)
    if (elapsed_times.length === 0) {
      return 0.0
    }
    return elapsed_times[elapsed_times.length - 1]
  }

  ninputs(since: number | null): number {
    const counts = this.linear_status_counts(since)
    if (counts.length === 0) {
      return 0
    }
    return counts[counts.length - 1].sum()
  }

  _cumsum<T>(
    cache: Map<number, [number, T[]]>,
    attr: keyof Report,
    add: (a: T, b: T) => T,
    since: number | null,
    initial: T,
  ): T[] {
    if (since === null) {
      since = -Infinity
    }

    if (cache.has(since)) {
      const [start_idx, cumsum] = cache.get(since)!
      if (cumsum.length < this.linear_reports.slice(start_idx).length) {
        // extend cumsum with any new reports
        let running = cumsum.length > 0 ? cumsum[cumsum.length - 1] : initial
        for (const report of this.linear_reports.slice(start_idx + cumsum.length)) {
          running = add(running, report[attr] as T)
          cumsum.push(running)
        }
        cache.set(since, [start_idx, cumsum])
      }
      return cumsum
    }

    const cumsum: T[] = []
    const start_idx = bisectRight(
      this.linear_reports,
      since,
      r => r.timestamp_monotonic!,
    )
    let running = initial
    for (const report of this.linear_reports.slice(start_idx)) {
      running = add(running, report[attr] as T)
      cumsum.push(running)
    }
    cache.set(since, [start_idx, cumsum])
    return cumsum
  }

  linear_status_counts(since: number | null): StatusCounts[] {
    return this._cumsum(
      this._status_counts_cumsum,
      "status_counts_diff",
      (a, b) => a.add(b),
      since,
      new StatusCounts(),
    )
  }

  linear_elapsed_time(since: number | null): number[] {
    return this._cumsum(
      this._elapsed_time_cumsum,
      "elapsed_time_diff",
      (a, b) => a + b,
      since,
      0.0,
    )
  }
}
