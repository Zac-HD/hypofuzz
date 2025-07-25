import { Report, StatusCounts } from "../../types/dashboard"

export class GraphReport {
  constructor(
    public nodeid: string,
    public linear_status_counts: StatusCounts,
    public linear_elapsed_time: number,
    public behaviors: number,
    public fingerprints: number,
  ) {}

  static fromReport(nodeid: string, report: Report): GraphReport {
    return new GraphReport(
      nodeid,
      report.status_counts,
      report.elapsed_time,
      report.behaviors,
      report.fingerprints,
    )
  }
}

export interface GraphLine {
  url: string | null
  reports: GraphReport[]
  color: string
}
