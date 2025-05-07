import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
} from "react"
import { Observation, Report, Test } from "../types/dashboard"
import JSON5 from "json5"

interface WebSocketEvent {
  type: "save" | "initial"
  data: any
}

interface DataContextType {
  tests: Map<string, Test>
  socket: WebSocket | null
}

const DataContext = createContext<DataContextType | null>(null)

interface DataProviderProps {
  children: React.ReactNode
  nodeid?: string
}

export function DataProvider({ children, nodeid }: DataProviderProps) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [tests, setTests] = useState<Map<string, Test>>(new Map())
  const [isLoading, setIsLoading] = useState(true)
  const testsRef = useRef(tests)

  // we want access to the latest value of `tests` inside the "save" event. React only
  // updates the value of `tests` when the component re-renders, which I think is only
  // when the useEffect triggers? so never, because we only load once per page.
  //
  // Instead, hold a ref handle to the current tests so it's always up to date.
  //
  // there's probably a better way to do this...
  useEffect(() => {
    testsRef.current = tests
  }, [tests])

  useEffect(() => {
    // import.meta.url is relative to the assets/ directory, so this is assets/dashboard_state.json
    fetch(new URL("dashboard_state.json", import.meta.url))
      .then(async response => {
        const data = await JSON5.parse(await response.text())
        if (data) {
          setTests(
            new Map(
              Object.entries(data.tests).map(([nodeid, data]) => [
                nodeid,
                Test.fromJson(data),
              ]),
            ),
          )
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
      if (nodeid) {
        url.searchParams.set("nodeid", nodeid)
      }

      const ws = new WebSocket(url)

      ws.onmessage = event => {
        // observability reports use e.g. Infinity, which is invalid in standard json but valid
        // in json5.
        const message = JSON5.parse(event.data) as WebSocketEvent

        switch (message.type) {
          case "initial":
            setTests(
              new Map(
                Object.entries(message.data).map(([nodeid, data]) => [
                  nodeid,
                  Test.fromJson(data),
                ]),
              ),
            )
            setIsLoading(false)
            break
          case "save":
            // this is a differential message. depending on the type of the save event, we'll do
            // something to the appropriate attribute on Test.
            switch (message.data.type) {
              case "report": {
                const report = Report.fromJson(message.data.data)
                const test = testsRef.current.get(report.nodeid)!
                test.addReport(report)
                // update react state to trigger a re-render on outside components that have a
                // useEffect dependency on `tests`
                setTests(new Map(testsRef.current))
                break
              }
              case "failure": {
                const failure = Observation.fromJson(message.data.data)
                const test = testsRef.current.get(failure.property)!
                test.failure = failure
                // trigger react re-render
                setTests(new Map(testsRef.current))
                break
              }
              // TODO: save events for test.rolling_observations and test.covering_observations
            }
            break
        }
      }

      setSocket(ws)

      return () => {
        ws.close()
      }
    }
  }, [nodeid])

  if (isLoading) {
    return null
  }

  return (
    <DataContext.Provider value={{ tests, socket }}>
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
