import React, { createContext, useContext, useEffect, useState } from "react"
import { Report, Metadata } from "../types/dashboard"

interface WebSocketEvent {
  type: "save" | "initial" | "metadata"
  data: unknown
  reports?: unknown
  metadata?: unknown
}

interface DataContextType {
  reports: Record<string, Report[]>
  metadata: Record<string, Metadata>
  socket: WebSocket | null
}

const DataContext = createContext<DataContextType | null>(null)

interface DataProviderProps {
  children: React.ReactNode
  nodeId?: string
}

export function DataProvider({ children, nodeId }: DataProviderProps) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [reports, setReports] = useState<Record<string, Report[]>>({})
  const [metadata, setMetadata] = useState<Record<string, Metadata>>({})
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    fetch("/assets/dashboard_state.json")
      .then(response => response.json())
      .then(data => {
        if (data) {
          setReports(data.reports || {})
          setMetadata(data.metadata || {})
          setIsLoading(false)
          return
        }
        setupWebSocket()
      })
      .catch(() => {
        setupWebSocket()
      })

    function setupWebSocket() {
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
            setReports(message.reports as Record<string, Report[]>)
            setMetadata(message.metadata as Record<string, Metadata>)
            setIsLoading(false)
            break
          case "save":
            setReports(currentReports => {
              const newReports = { ...(currentReports ?? {}) }
              const report = message.data as Report
              const nodeid = report.nodeid
              if (!newReports[nodeid]) {
                newReports[nodeid] = []
              }
              newReports[nodeid] = [...newReports[nodeid], report]
              return newReports
            })
            break
          case "metadata":
            setMetadata(currentMetadata => {
              const newMetadata = { ...(currentMetadata ?? {}) }
              const metadata = message.data as Metadata
              newMetadata[metadata.nodeid] = metadata
              return newMetadata
            })
            break
        }
        // sort reports every time. a bit inefficient, and we may want to remove this
        // when the backend or websocket events make stronger ordering guarantees.
        setReports(currentReports => {
          for (const nodeid in currentReports) {
            currentReports[nodeid].sort(
              (a, b) => a.elapsed_time - b.elapsed_time,
            )
          }
          return currentReports
        })
      }

      setSocket(ws)

      return () => {
        ws.close()
      }
    }
  }, [nodeId])

  if (isLoading) {
    return null
  }

  return (
    <DataContext.Provider value={{ reports, metadata, socket }}>
      {children}
    </DataContext.Provider>
  )
}

export function useData() {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error("useData must be used within a DataProvider")
  }
  return context
}
