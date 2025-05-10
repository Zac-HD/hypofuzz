import { mapsEqual, setsEqual, sum } from "../utils/utils"

abstract class Dataclass<T> {
  withProperties(props: Partial<T>): T {
    return Object.assign(Object.create(this.constructor.prototype), this, props) as T
  }
}

class StatusCounts extends Dataclass<StatusCounts> {
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
  constructor(
    public database_key: string,
    public nodeid: string,
    public elapsed_time: number,
    public timestamp: number,
    public worker: WorkerIdentity,
    public status_counts: StatusCounts,
    public branches: number,
    public since_new_cov: number | null,
    public phase: Phase,
  ) {
    super()
  }

  get ninputs() {
    return sum(this.status_counts.counts.values())
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
      data.since_new_cov,
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
  public status_counts: StatusCounts
  public elapsed_time: number
  public linear_reports: Report[]

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
    this.status_counts = new StatusCounts()
    this.elapsed_time = 0.0
    this.linear_reports = []

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
      console.assert(reports[i].elapsed_time <= reports[i + 1].elapsed_time)
      console.assert(reports[i].status_counts <= reports[i + 1].status_counts)
      console.assert(reports[i].timestamp <= reports[i + 1].timestamp)
    }
  }

  _check_invariants() {
    this._assert_reports_ordered(this.linear_reports)

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

    let total_status_counts = new StatusCounts()
    for (const reports of this.reports_by_worker.values()) {
      total_status_counts = total_status_counts.add(
        reports[reports.length - 1].status_counts,
      )
    }
    console.assert(mapsEqual(this.status_counts.counts, total_status_counts.counts))
  }

  add_report(report: Report) {
    // This function implements Test.add_report in python. Make sure to keep the
    // two versions in sync.

    const workerReports = this.reports_by_worker.get(report.worker.uuid)
    const last_report = workerReports ? workerReports[workerReports.length - 1] : null

    if (last_report && last_report.timestamp > report.timestamp) {
      // out of order report
      return
    }

    const last_status_counts = last_report
      ? last_report.status_counts
      : new StatusCounts()
    const last_elapsed_time = last_report ? last_report.elapsed_time : 0.0

    const status_counts_diff = report.status_counts.subtract(last_status_counts)
    const elapsed_time_diff = report.elapsed_time - last_elapsed_time
    console.assert(
      Array.from(status_counts_diff.counts.values()).every(count => count >= 0),
    )
    console.assert(elapsed_time_diff >= 0.0)

    const linearized_report = report.withProperties({
      status_counts: this.status_counts.add(status_counts_diff),
      elapsed_time: this.elapsed_time + elapsed_time_diff,
    })

    this.status_counts = this.status_counts.add(status_counts_diff)
    this.elapsed_time += elapsed_time_diff
    if (!(report.worker.uuid in this.reports_by_worker)) {
      this.reports_by_worker.set(report.worker.uuid, [])
    }
    this.reports_by_worker.get(report.worker.uuid)!.push(report)

    if (report.phase !== Phase.REPLAY) {
      this.linear_reports.push(linearized_report)
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

  get ninputs() {
    return sum(this.status_counts.counts.values())
  }

  get branches() {
    if (this.linear_reports.length === 0) {
      return 0
    }
    return this.linear_reports[this.linear_reports.length - 1].branches
  }

  get since_new_cov() {
    if (this.linear_reports.length === 0) {
      return null
    }
    return this.linear_reports[this.linear_reports.length - 1].since_new_cov
  }
}
