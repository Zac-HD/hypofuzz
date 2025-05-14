import { bisectLeft, bisectRight, setsEqual, sum } from "../utils/utils"

abstract class Dataclass<T> {
  withProperties(props: Partial<T>): T {
    return Object.assign(Object.create(this.constructor.prototype), this, props) as T
  }
}

export class StatusCounts extends Dataclass<StatusCounts> {
  constructor(
    public counts: Map<Status, number> = new Map([
      [Status.OVERRUN, 0],
      [Status.INVALID, 0],
      [Status.VALID, 0],
      [Status.INTERESTING, 0],
    ]),
  ) {
    super()
  }

  static fromJson(data: any): StatusCounts {
    const counts = new Map<Status, number>([
      [Status.OVERRUN, 0],
      [Status.INVALID, 0],
      [Status.VALID, 0],
      [Status.INTERESTING, 0],
    ])

    for (const [status, count] of Object.entries(data)) {
      console.assert(typeof count === "number")
      counts.set(Number(status) as Status, count as number)
    }
    return new StatusCounts(counts)
  }

  add(statuses: StatusCounts): StatusCounts {
    const newStatuses = new Map(this.counts)
    for (const [status, count] of statuses.counts.entries()) {
      newStatuses.set(status, newStatuses.get(status)! + count)
    }
    return new StatusCounts(newStatuses)
  }

  subtract(statuses: StatusCounts): StatusCounts {
    const newStatusCounts = new Map(this.counts)
    for (const [status, count] of statuses.counts.entries()) {
      newStatusCounts.set(status, newStatusCounts.get(status)! - count)
    }
    return new StatusCounts(newStatusCounts)
  }

  sum(): number {
    return sum(this.counts.values())
  }
}

export enum Status {
  OVERRUN = 0,
  INVALID = 1,
  VALID = 2,
  INTERESTING = 3,
}

export enum Phase {
  GENERATE = "generate",
  REPLAY = "replay",
  DISTILL = "distill",
  SHRINK = "shrink",
  FAILED = "failed",
}

export interface WorkerIdentity {
  uuid: string
  operating_system: string
  python_version: string
  hypothesis_version: string
  hypofuzz_version: string
  pid: number
  hostname: string
  pod_name: string | null
  pod_namespace: string | null
  node_name: string | null
  pod_ip: string | null
  container_id: string | null
  git_hash: string | null
}

export class Report extends Dataclass<Report> {
  public status_counts_diff: StatusCounts | null
  public elapsed_time_diff: number | null
  public timestamp_monotonic: number | null

  constructor(
    public database_key: string,
    public nodeid: string,
    public elapsed_time: number,
    public timestamp: number,
    public worker: WorkerIdentity,
    public status_counts: StatusCounts,
    public branches: number,
    public since_new_branch: number | null,
    public phase: Phase,
  ) {
    super()
    this.status_counts_diff = null
    this.elapsed_time_diff = null
    this.timestamp_monotonic = null
  }

  get ninputs(): number {
    return this.status_counts.sum()
  }

  static fromJson(data: any): Report {
    return new Report(
      data.database_key,
      data.nodeid,
      data.elapsed_time,
      data.timestamp,
      data.worker,
      StatusCounts.fromJson(data.status_counts),
      data.branches,
      data.since_new_branch,
      data.phase,
    )
  }
}

enum ObservationStatus {
  PASSED = "passed",
  FAILED = "failed",
  GAVE_UP = "gave_up",
}

export class Observation extends Dataclass<Observation> {
  // https://hypothesis.readthedocs.io/en/latest/reference/integrations.html#test-case
  constructor(
    public type: string,
    public status: ObservationStatus,
    public status_reason: string,
    public representation: string,
    // arguments is a reserved keyword in javascript
    public arguments_: Map<string, any>,
    public how_generated: string,
    public features: Map<string, any>,
    public timing: Map<string, any>,
    public metadata: Map<string, any>,
    public property: string,
    public run_start: number,
  ) {
    super()
  }

  static fromJson(data: any): Observation {
    return new Observation(
      data.type,
      data.status,
      data.status_reason,
      data.representation,
      new Map(Object.entries(data.arguments)),
      data.how_generated,
      new Map(Object.entries(data.features)),
      new Map(Object.entries(data.timing)),
      new Map(Object.entries(data.metadata)),
      data.property,
      data.run_start,
    )
  }
}

export enum TestStatus {
  FAILED = 0,
  SHRINKING = 1,
  RUNNING = 2,
  WAITING = 3,
}

export class Test extends Dataclass<Test> {
  // if it's been this long since the last report in seconds, consider the test status
  // to be "waiting" instead of "running"
  static WAITING_STATUS_DURATION = 120

  public observations_loaded: boolean
  public linear_reports: Report[]
  private _status_counts_cumsum: Map<number, [number, StatusCounts[]]>
  private _elapsed_time_cumsum: Map<number, [number, number[]]>

  constructor(
    public database_key: string,
    public nodeid: string,
    public rolling_observations: Observation[],
    public corpus_observations: Observation[],
    public failure: Observation | null,
    public reports_by_worker: Map<string, Report[]>,
  ) {
    super()
    this.observations_loaded = false
    this.linear_reports = []
    // TODO we should use an actual LRUCache for memory here, like in python.
    // https://github.com/isaacs/node-lru-cache looks like a good option
    this._status_counts_cumsum = new Map()
    this._elapsed_time_cumsum = new Map()

    const reports_by_worker_ = this.reports_by_worker
    this.reports_by_worker = new Map()

    // TODO: use k-way merge for performance?
    const sorted_reports = Array.from(reports_by_worker_.values())
      .flat()
      .sortKey(report => report.timestamp)
    for (const report of sorted_reports) {
      this.add_report(report)
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
      data.failure ? Observation.fromJson(data.failure) : null,
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

    for (const [worker_uuid, reports] of this.reports_by_worker.entries()) {
      console.assert(
        setsEqual(new Set(reports.map(r => r.nodeid)), new Set([this.nodeid])),
      )
      console.assert(
        setsEqual(
          new Set(reports.map(r => r.database_key)),
          new Set([this.database_key]),
        ),
      )
      console.assert(
        setsEqual(new Set(reports.map(r => r.worker.uuid)), new Set([worker_uuid])),
      )
      this._assert_reports_ordered(reports)
    }
  }

  add_report(report: Report) {
    // This function implements Test.add_report in python. Make sure to keep the
    // two versions in sync.

    const workerReports = this.reports_by_worker.get(report.worker.uuid)
    const last_report =
      this.linear_reports.length > 0
        ? this.linear_reports[this.linear_reports.length - 1]
        : null
    const last_report_worker = workerReports
      ? workerReports[workerReports.length - 1]
      : null
    if (last_report_worker && last_report_worker.elapsed_time > report.elapsed_time) {
      // out of order report
      return
    }

    console.assert(last_report === null || last_report.timestamp_monotonic !== null)
    const last_status_counts = last_report_worker
      ? last_report_worker.status_counts
      : new StatusCounts()
    const last_elapsed_time = last_report_worker ? last_report_worker.elapsed_time : 0.0
    const status_counts_diff = report.status_counts.subtract(last_status_counts)
    const elapsed_time_diff = report.elapsed_time - last_elapsed_time
    const timestamp_monotonic = last_report
      ? Math.max(report.timestamp, last_report.timestamp_monotonic! + elapsed_time_diff)
      : report.timestamp
    console.assert(
      Array.from(status_counts_diff.counts.values()).every(count => count >= 0),
    )
    console.assert(elapsed_time_diff >= 0.0)
    console.assert(timestamp_monotonic >= 0.0)

    const linear_report = report.withProperties({
      status_counts_diff: status_counts_diff,
      elapsed_time_diff: elapsed_time_diff,
      timestamp_monotonic: timestamp_monotonic,
    })

    if (!(report.worker.uuid in this.reports_by_worker)) {
      this.reports_by_worker.set(report.worker.uuid, [])
    }
    this.reports_by_worker.get(report.worker.uuid)!.push(linear_report)
    if (linear_report.phase !== Phase.REPLAY) {
      this.linear_reports.push(linear_report)
    }

    this._check_invariants()
  }

  get status() {
    if (this.failure) {
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

  get branches() {
    if (this.linear_reports.length === 0) {
      return 0
    }
    return this.linear_reports[this.linear_reports.length - 1].branches
  }

  get since_new_branch() {
    // TODO take linearization into account properly here. I think we want "linearized
    // inputs since branch count last increased". Iterate backwards over linear_status_counts?
    if (this.linear_reports.length === 0) {
      return null
    }
    return this.linear_reports[this.linear_reports.length - 1].since_new_branch
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
