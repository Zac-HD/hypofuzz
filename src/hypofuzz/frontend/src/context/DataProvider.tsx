import React, { createContext, useContext, useEffect, useState, useRef } from "react"
import { Observation, Report, Test } from "../types/dashboard"
import JSON5 from "json5"

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
    // load data from local dashboard state json files iff the appropriate env var was set
    // during building.
    if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
      fetch(new URL(/* @vite-ignore */ "dashboard_state/tests.json", import.meta.url))
        .then(response => response.text())
        .then(text => JSON5.parse(text) as Record<string, any>)
        .then(data => {
          const tests = new Map(
            Object.entries(data).map(([nodeid, data]) => [nodeid, Test.fromJson(data)]),
          )
          setTests(tests)
          setIsLoading(false)
        })

      // json.parse is sync (blocks ui) and expensive. Push it to a background worker to make it async.
      // We pay a small serialization cost; ~5% by my measurement.
      const worker = new Worker(new URL("./jsonWorker.js", import.meta.url))
      fetch(
        new URL(
          /* @vite-ignore */ "dashboard_state/observations.json",
          import.meta.url,
        ),
      )
        .then(response => response.text())
        .then(text => {
          return new Promise<Record<string, { rolling: any[]; corpus: any[] }>>(
            resolve => {
              worker.onmessage = e => resolve(e.data)
              worker.postMessage(text)
            },
          )
        })
        .then(observationsData => {
          for (const [test_id, testObservations] of Object.entries(observationsData)) {
            const test = testsRef.current.get(test_id)!
            test.rolling_observations = testObservations.rolling.map(
              Observation.fromJson,
            )
            test.corpus_observations = testObservations.corpus.map(Observation.fromJson)
            test.observations_loaded = true
          }
          setTests(new Map(testsRef.current))
        })

      return () => worker.terminate()
    }

    const url = new URL(
      `ws${window.location.protocol === "https:" ? "s" : ""}://${window.location.host}/ws`,
    )
    if (nodeid) {
      url.searchParams.set("nodeid", nodeid)
    }

    const ws = new WebSocket(url)

    ws.onmessage = event => {
      // split the message into the header and the body, to allow for parsing the
      // body with either JSON (faster) or JSON5 (allows e.g. Infinity) depending on
      // the type of the data. We don't want to parse with JSON5 unless necessary.
      //
      // The format is an extremely simple pipe separator.

      // note: data.split("|", 2) is incorrect, as it drops everything after the second pipe, unlike python's split
      const pipeIndex = event.data.indexOf("|")
      let header = event.data.slice(0, pipeIndex)
      let data = event.data.slice(pipeIndex + 1)
      header = JSON.parse(header)

      switch (header.type) {
        case "initial":
          switch (header.initial_type) {
            case "tests": {
              // this is only json 5 because test.failure is an observation. Should we split that out to "observations"
              // as well?
              data = JSON5.parse(data)
              setTests(
                new Map(
                  Object.entries(data).map(([nodeid, data]) => [
                    nodeid,
                    Test.fromJson(data),
                  ]),
                ),
              )
              setIsLoading(false)
              break
            }
            case "observations": {
              data = JSON5.parse(data)
              for (const [test_id, observationsData] of Object.entries(data)) {
                // this relies on initial_type == "tests" being parsed first, but I don't think
                // this is guaranteed in async land. need to refactor each initial_type to create an
                // empty test and set its attributes appropriately.
                const test = testsRef.current.get(test_id)!
                test.rolling_observations = (observationsData as any).rolling.map(
                  Observation.fromJson,
                )
                test.corpus_observations = (observationsData as any).corpus.map(
                  Observation.fromJson,
                )
                test.observations_loaded = true
                setTests(new Map(testsRef.current))
              }
              break
            }
          }
          break
        case "save":
          // this is a differential message. depending on the type of the event, we'll do
          // something to the appropriate attribute on Test.
          switch (header.key) {
            case "report": {
              data = JSON.parse(data)
              const report = Report.fromJson(data)
              const test = testsRef.current.get(report.nodeid)!
              test.add_report(report)
              // update react state to trigger a re-render on outside components that have a
              // useEffect dependency on `tests`
              setTests(new Map(testsRef.current))
              break
            }
            case "failure": {
              // observability reports use e.g. Infinity, which is invalid in standard json
              // but valid in json5.
              data = JSON5.parse(data)
              const failure = Observation.fromJson(data)
              const test = testsRef.current.get(failure.property)!
              test.failure = failure
              // trigger react re-render
              setTests(new Map(testsRef.current))
              break
            }
            case "rolling_observation": {
              data = JSON5.parse(data)
              const observation = Observation.fromJson(data)
              const test = testsRef.current.get(observation.property)!
              test.rolling_observations.push(observation)
              // keep only the most recent 300 rolling observations, by run_start
              //
              // this is a good candidate for a proper nlogn SortedList
              test.rolling_observations = test.rolling_observations
                .sortKey(observation => observation.run_start)
                .slice(-300)
              setTests(new Map(testsRef.current))
              break
            }
            case "corpus_observation": {
              data = JSON5.parse(data)
              const observation = Observation.fromJson(data)
              const test = testsRef.current.get(observation.property)!
              test.corpus_observations.push(observation)
              setTests(new Map(testsRef.current))
              break
            }
          }
          break
      }
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
  }, [nodeid])

  if (isLoading) {
    return null
  }

  return (
    <DataContext.Provider value={{ tests, socket }}>{children}</DataContext.Provider>
  )
}

export function useData() {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error("useData must be used within a DataProvider")
  }
  return context
}
