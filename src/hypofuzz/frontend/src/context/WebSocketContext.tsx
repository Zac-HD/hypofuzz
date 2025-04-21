import React, { createContext, useContext, useEffect, useState } from "react"
import {
  Report,
  Metadata,
  LinearReports,
  Phase,
  Status,
} from "../types/dashboard"

export interface WebSocketRequest {
  page: "overview" | "test"
  node_id?: string
}

interface WebSocketContextType {
  reports: Map<string, Report[]>
  metadata: Map<string, Metadata>
  socket: WebSocket | null
}

interface WebSocketEvent {
  type: "save" | "initial" | "metadata"
  data: unknown
  reports?: unknown
  metadata?: unknown
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

interface WebSocketProviderProps {
  children: React.ReactNode
  nodeId?: string
}

function addStatusCounts(
  statuses1: Map<Status, number>,
  statuses2: Map<Status, number>,
) {
  const newStatuses = new Map(statuses1)
  for (const [status, count] of statuses2.entries()) {
    newStatuses.set(status, (newStatuses.get(status) ?? 0) + count)
  }
  return newStatuses
}

function subStatusCounts(
  statuses1: Map<Status, number>,
  statuses2: Map<Status, number>,
) {
  const newStatusCounts = new Map(statuses1)
  for (const [status, count] of statuses2.entries()) {
    newStatusCounts.set(status, (newStatusCounts.get(status) ?? 0) - count)
  }
  return newStatusCounts
}

export function WebSocketProvider({
  children,
  nodeId,
}: WebSocketProviderProps) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [reports, setReports] = useState<Map<string, LinearReports>>(new Map())
  const [metadata, setMetadata] = useState<Map<string, Metadata>>(new Map())

  useEffect(() => {
    const url = new URL(
      `ws${window.location.protocol === "https:" ? "s" : ""}://${window.location.host}/ws`,
    )
    if (nodeId) {
      url.searchParams.set("node_id", nodeId)
    }

    const ws = new WebSocket(url)

    ws.onmessage = event => {
      const message = JSON.parse(event.data) as WebSocketEvent

      switch (message.type) {
        case "initial":
          const reports = new Map<string, LinearReports>(
            Object.entries(
              message.reports as Record<string, LinearReports>,
            ).map(([nodeId, data]) => [nodeId, LinearReports.fromJson(data)]),
          )
          setReports(reports)
          setMetadata(
            new Map<string, Metadata>(
              Object.entries(message.metadata as Record<string, Metadata>).map(
                ([nodeId, data]) => [nodeId, Metadata.fromJson(data)],
              ),
            ),
          )
          break
        case "save":
          setReports(currentReports => {
            const report = Report.fromJson(message.data)
            if (report.phase === Phase.REPLAY) {
              return currentReports
            }
            const newReports = new Map(currentReports)
            // this happens if we start working on a nodeid that wasn't in our "initial"
            // report from the dashboard. TODO do we want to send the structure for *all*
            // collected tests from the dashboard, even if empty?
            if (!newReports.has(report.nodeid)) {
              newReports.set(report.nodeid, {
                reports: [],
                offsets: {
                  status_counts: new Map<string, Map<Status, number>>(),
                  elapsed_time: new Map<string, number>(),
                },
              })
            }
            const nodeReports = newReports.get(report.nodeid)!.reports
            const offsets = newReports.get(report.nodeid)!.offsets
            if (!offsets.status_counts.has(report.worker.uuid)) {
              offsets.status_counts.set(
                report.worker.uuid,
                new Map([
                  [Status.OVERRUN, 0],
                  [Status.INVALID, 0],
                  [Status.VALID, 0],
                  [Status.INTERESTING, 0],
                ]),
              )
              offsets.elapsed_time.set(report.worker.uuid, 0)
            }
            const offsetsStatuses = offsets.status_counts.get(
              report.worker.uuid,
            )!
            const newStatuses = subStatusCounts(
              report.status_counts,
              offsetsStatuses,
            )

            const newElapsedTime =
              report.elapsed_time -
              offsets.elapsed_time.get(report.worker.uuid)!

            if (nodeReports.length > 0) {
              const latestReport = nodeReports[nodeReports.length - 1]
              const updatedReport = new Report(
                report.database_key,
                report.nodeid,
                latestReport.elapsed_time + newElapsedTime,
                report.timestamp,
                report.worker,
                addStatusCounts(latestReport.status_counts, newStatuses),
                report.branches,
                report.since_new_cov,
                report.phase,
              )
              nodeReports.push(updatedReport)
            } else {
              nodeReports.push(report)
            }

            offsets.elapsed_time.set(
              report.worker.uuid,
              offsets.elapsed_time.get(report.worker.uuid)! + newElapsedTime,
            )
            offsets.status_counts.set(
              report.worker.uuid,
              addStatusCounts(
                offsets.status_counts.get(report.worker.uuid)!,
                newStatuses,
              ),
            )
            return newReports
          })
          break
        case "metadata":
          setMetadata(currentMetadata => {
            const newMetadata = new Map(currentMetadata)
            const metadata = Metadata.fromJson(message.data)
            newMetadata.set(metadata.nodeid, metadata)
            return newMetadata
          })
          break
      }
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
  }, [nodeId])

  if (reports === null || metadata === null) {
    return null // Don't render anything until we have initial data
  }

  // the offsets are an internal detail of the websocket, for use in implementing
  // the "save" event linearization. Don't return them outside of the websocket,
  // for convenience.
  const justReports = new Map<string, Report[]>(
    Array.from(reports.entries()).map(([nodeId, reports]) => [
      nodeId,
      reports.reports,
    ]),
  )

  return (
    <WebSocketContext.Provider
      value={{ reports: justReports, metadata, socket }}
    >
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocket() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error("useWebSocket must be used within a WebSocketProvider")
  }
  return context
}
