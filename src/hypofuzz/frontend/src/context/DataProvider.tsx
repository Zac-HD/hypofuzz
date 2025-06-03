import React, {
  createContext,
  useContext,
  useEffect,
  useReducer,
  useState,
} from "react"
import { Observation, Report, Test } from "../types/dashboard"

interface DataContextType {
  tests: Map<string, Test>
  socket: WebSocket | null
  doLoadData: (nodeid: string | null) => void
}

const DataContext = createContext<DataContextType | null>(null)

interface DataProviderProps {
  children: React.ReactNode
}

enum DashboardEventType {
  ADD_TESTS = 1,
  ADD_REPORTS = 2,
  ADD_ROLLING_OBSERVATIONS = 3,
  ADD_CORPUS_OBSERVATIONS = 4,
  SET_FAILURE = 5,
}

type TestsAction =
  | {
      type: DashboardEventType.ADD_TESTS
      tests: {
        database_key: string
        nodeid: string
        failure: Observation | null
      }[]
    }
  | {
      type: DashboardEventType.ADD_REPORTS
      nodeid: string
      worker_uuid: string
      reports: Report[]
    }
  | { type: DashboardEventType.SET_FAILURE; failure: Observation }
  | {
      type: DashboardEventType.ADD_ROLLING_OBSERVATIONS
      nodeid: string
      observations: Observation[]
    }
  | {
      type: DashboardEventType.ADD_CORPUS_OBSERVATIONS
      nodeid: string
      observations: Observation[]
    }

function testsReducer(
  state: Map<string, Test>,
  action: TestsAction,
): Map<string, Test> {
  const newState = new Map(state)

  function getOrCreateTest(nodeid: string): Test {
    if (newState.has(nodeid)) {
      return newState.get(nodeid)!
    } else {
      const test = new Test(null, nodeid, [], [], null, new Map())
      newState.set(test.nodeid, test)
      return test
    }
  }

  switch (action.type) {
    case DashboardEventType.ADD_TESTS: {
      const { tests } = action
      for (const { database_key, nodeid, failure } of tests) {
        const test = getOrCreateTest(nodeid)
        test.database_key = database_key
        test.failure = failure ? Observation.fromJson(failure) : null
      }
      return newState
    }

    case DashboardEventType.ADD_REPORTS: {
      const { nodeid, worker_uuid, reports } = action
      const test = getOrCreateTest(nodeid)
      for (const report of reports) {
        test.add_report(worker_uuid, report)
      }
      return newState
    }

    case DashboardEventType.SET_FAILURE: {
      const { failure } = action
      const test = getOrCreateTest(failure.property)
      test.failure = failure
      return newState
    }

    case DashboardEventType.ADD_ROLLING_OBSERVATIONS: {
      const { nodeid, observations } = action
      const test = getOrCreateTest(nodeid)
      test.rolling_observations.push(...observations)
      // keep only the most recent 300 rolling observations, by run_start
      //
      // this is a good candidate for a proper nlogn SortedList
      test.rolling_observations = test.rolling_observations
        .sortKey(observation => observation.run_start)
        .slice(-300)
      return newState
    }

    case DashboardEventType.ADD_CORPUS_OBSERVATIONS: {
      const { nodeid, observations } = action
      const test = getOrCreateTest(nodeid)
      test.corpus_observations.push(...observations)
      return newState
    }

    default:
      throw new Error("non-exhaustive switch in testsReducer")
  }
}

export function DataProvider({ children }: DataProviderProps) {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [tests, dispatch] = useReducer(testsReducer, new Map<string, Test>())
  const [loadData, setLoadData] = useState(false)
  const [nodeid, setNodeid] = useState<string | null>(null)

  const doLoadData = (nodeid: string | null) => {
    setLoadData(true)
    setNodeid(nodeid)
  }

  useEffect(() => {
    if (!loadData) {
      return
    }

    // load data from local dashboard state json files iff the appropriate env var was set
    // during building.
    if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
      fetch(new URL(/* @vite-ignore */ "dashboard_state/tests.json", import.meta.url))
        .then(response => response.text())
        .then(text => JSON.parse(text) as Record<string, any>)
        .then(data => {
          Object.entries(data).forEach(([nodeid, testData]) => {
            dispatch({
              type: DashboardEventType.ADD_TESTS,
              tests: [
                {
                  database_key: testData.database_key,
                  nodeid: nodeid,
                  failure: testData.failure,
                },
              ],
            })

            for (const [worker_uuid, reports] of Object.entries(
              testData.reports_by_worker,
            )) {
              dispatch({
                type: DashboardEventType.ADD_REPORTS,
                nodeid: nodeid,
                worker_uuid: worker_uuid,
                reports: (reports as any[]).map(report =>
                  Report.fromJson(worker_uuid, report),
                ),
              })
            }
          })
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
        .then(data => {
          for (const [nodeid, test] of Object.entries(data)) {
            dispatch({
              type: DashboardEventType.ADD_ROLLING_OBSERVATIONS,
              nodeid: nodeid,
              observations: test.rolling.map(Observation.fromJson),
            })
            dispatch({
              type: DashboardEventType.ADD_CORPUS_OBSERVATIONS,
              nodeid: nodeid,
              observations: test.corpus.map(Observation.fromJson),
            })
          }
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
      // split the message into the header and the body. The format is an extremely simple pipe separator.

      // note: data.split("|", 2) is incorrect, as it drops everything after the second pipe, unlike python's split
      const pipeIndex = event.data.indexOf("|")
      let header = event.data.slice(0, pipeIndex)
      let data = event.data.slice(pipeIndex + 1)
      header = JSON.parse(header)

      switch (Number(header.type)) {
        case DashboardEventType.ADD_TESTS: {
          data = JSON.parse(data)
          dispatch({
            type: DashboardEventType.ADD_TESTS,
            tests: data.tests.map((test: any) => ({
              database_key: test.database_key,
              nodeid: test.nodeid,
              failure: test.failure,
            })),
          })
          break
        }

        case DashboardEventType.ADD_REPORTS: {
          data = JSON.parse(data)
          dispatch({
            type: DashboardEventType.ADD_REPORTS,
            nodeid: data.nodeid,
            worker_uuid: data.worker_uuid,
            reports: (data.reports as any[]).map(report =>
              Report.fromJson(data.worker_uuid, report),
            ),
          })
          break
        }

        case DashboardEventType.ADD_CORPUS_OBSERVATIONS: {
          data = JSON.parse(data)
          dispatch({
            type: DashboardEventType.ADD_CORPUS_OBSERVATIONS,
            nodeid: data.nodeid,
            observations: data.observations.map(Observation.fromJson),
          })
          break
        }

        case DashboardEventType.ADD_ROLLING_OBSERVATIONS: {
          data = JSON.parse(data)
          dispatch({
            type: DashboardEventType.ADD_ROLLING_OBSERVATIONS,
            nodeid: data.nodeid,
            observations: data.observations.map(Observation.fromJson),
          })
          break
        }

        default:
          throw new Error(`Unknown event type: ${header.type}`)
      }
    }

    setSocket(ws)

    return () => {
      ws.close()
    }
    // a single DataProvider is created for the entire lifetime of a tab. We want to re-load
    // the provided data whenever we change the nodeid (e.g. going from overview to a specific
    // test page) or we go from a page which doesn't want data (because it didn't call useData)
    // to one that does.
  }, [nodeid, loadData])

  return (
    <DataContext.Provider value={{ tests, socket, doLoadData }}>
      {children}
    </DataContext.Provider>
  )
}

export function useData(nodeid: string | null = null) {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error("useData must be used within a DataProvider")
  }

  context.doLoadData(nodeid)
  return context
}
