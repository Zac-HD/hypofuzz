import { Report, StatusCounts } from "../../types/dashboard"

export class GraphReport {
  constructor(
    public nodeid: string,
    public linear_status_counts: StatusCounts,
    public linear_elapsed_time: number,
    public behaviors: number,
    public fingerprints: number,
    public worker_uuid: string,
    public timestamp_monotonic: number,
  ) {}

  static fromReport(nodeid: string, report: Report): GraphReport {
    return new GraphReport(
      nodeid,
      report.status_counts,
      report.elapsed_time,
      report.behaviors,
      report.fingerprints,
      report.worker_uuid,
      report.timestamp_monotonic!,
    )
  }
}

export interface GraphLine {
  nodeid: string
  url: string | null
  reports: GraphReport[]
  color: string
  isActive: boolean
}
