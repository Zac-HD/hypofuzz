import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react"

import { ProgressBar } from "../components/ProgressBar"
import { NOT_PRESENT_STRING, PRESENT_STRING } from "../tyche/Tyche"
import { Failure, Observation, Report } from "../types/dashboard"
import { Test } from "../types/test"
import { useNotification } from "./NotificationProvider"

interface DataContextType {
  tests: Map<string, Test>
  socket: WebSocket | null
  doLoadData: (nodeid: string | null) => void
  testsLoaded: () => boolean
}

const DataContext = createContext<DataContextType | null>(null)

interface DataProviderProps {
  children: React.ReactNode
}

interface LoadingStatus {
  // the number of tests collected by the dashboard.
  count_tests: number | null
  // the number of tests the dashboard has fully loaded from the database so far.
  count_tests_loaded: number | null
}

enum DashboardEventType {
  SET_STATUS = 1,
  ADD_TESTS = 2,
  ADD_REPORTS = 3,
  ADD_OBSERVATIONS = 4,
  ADD_FAILURES = 5,
  SET_FAILURES = 6,
  TEST_LOAD_FINISHED = 7,
}

type TestsAction =
  | {
      type: DashboardEventType.SET_STATUS
      loading_status: LoadingStatus
    }
  | {
      type: DashboardEventType.ADD_TESTS
      tests: {
        database_key: string
        nodeid: string
        failures: Map<string, Failure>
      }[]
    }
  | {
      type: DashboardEventType.ADD_REPORTS
      nodeid: string
      worker_uuid: string
      reports: Report[]
    }
  | {
      type: DashboardEventType.ADD_FAILURES
      nodeid: string
      failures: Map<string, Failure>
    }
  | {
      type: DashboardEventType.ADD_OBSERVATIONS
      nodeid: string
      observation_type: "rolling" | "corpus"
      observations: Observation[]
    }
  | {
      type: DashboardEventType.TEST_LOAD_FINISHED
      nodeid: string
    }

function prepareObservations(observations: Observation[]) {
  // compute uniqueness
  const reprCounts = new Map<string, number>()
  observations.forEach(obs => {
    reprCounts.set(obs.representation, (reprCounts.get(obs.representation) || 0) + 1)
  })

  observations.forEach(observation => {
    const count = reprCounts.get(observation.representation)!
    observation.isUnique = count == 1
    observation.isDuplicate = count > 1
  })

  // We want tyche to be able to rely on observations having a value for every feature. This makes
  // things easier for e.g. the sorting logic. To support this, first make a set of all features.
  // Then, for each observation, if that feature is not present, insert it with value "Not present".
  //
  // Also, if an observation's feature value is ever "", change that to "Present". These come from
  // e.g. ``event(value)``, without an associated payload.
  const features = new Set<string>()
  observations.forEach(obs => {
    obs.features.forEach((_value, feature) => {
      features.add(feature)
    })
  })

  observations.forEach(obs => {
    features.forEach(feature => {
      if (!obs.features.has(feature)) {
        obs.features.set(feature, NOT_PRESENT_STRING)
      }
    })

    for (const [feature, value] of obs.features) {
      if (value === "") {
        obs.features.set(feature, PRESENT_STRING)
      }
    }
  })
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
      const test = new Test(null, nodeid, [], [], new Map(), new Map())
      newState.set(test.nodeid, test)
      return test
    }
  }

  switch (action.type) {
    case DashboardEventType.SET_STATUS: {
      return state
    }

    case DashboardEventType.ADD_TESTS: {
      const { tests } = action
      for (const { database_key, nodeid, failures } of tests) {
        const test = getOrCreateTest(nodeid)
        test.database_key = database_key
        failures.forEach((failure, interesting_origin) => {
          test.failures.set(interesting_origin, failure)
        })
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

    case DashboardEventType.ADD_FAILURES: {
      const { nodeid, failures } = action
      const test = getOrCreateTest(nodeid)
      failures.forEach((failure, interesting_origin) => {
        test.failures.set(interesting_origin, failure)
      })
      return newState
    }

    case DashboardEventType.ADD_OBSERVATIONS: {
      const { nodeid, observation_type, observations } = action
      const test = getOrCreateTest(nodeid)
      if (observation_type === "rolling") {
        test.rolling_observations.push(...observations)
        // keep only the most recent 300 rolling observations, by run_start
        //
        // this is a good candidate for a proper nlogn SortedList
        test.rolling_observations = test.rolling_observations
          .sortKey(observation => -observation.run_start)
          .slice(0, 300)
        prepareObservations(test.rolling_observations)
      } else {
        console.assert(observation_type === "corpus")
        test.corpus_observations.push(...observations)
        prepareObservations(test.corpus_observations)
      }
      return newState
    }

    case DashboardEventType.TEST_LOAD_FINISHED: {
      const { nodeid } = action
      const test = getOrCreateTest(nodeid)
      test.load_finished_at = Date.now()
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
  const [loadingStatus, setLoadingStatus] = useState<LoadingStatus>({
    count_tests: null,
    count_tests_loaded: null,
  })
  const { addNotification, updateNotification, dismissNotification } = useNotification()
  const statusNotification = useRef<number | null>(null)

  const doLoadData = useCallback((nodeid: string | null) => {
    setLoadData(true)
    setNodeid(nodeid)
  }, [])

  const testsLoaded = useCallback(() => {
    const now = Date.now()
    return (
      loadingStatus.count_tests_loaded !== null &&
      loadingStatus.count_tests !== null &&
      loadingStatus.count_tests_loaded === loadingStatus.count_tests &&
      Array.from(tests.values()).every(test => {
        if (test.load_finished_at === null) {
          return false
        }
        return now - test.load_finished_at > 200
      })
    )
  }, [loadingStatus, tests])

  useEffect(() => {
    if (!loadData) {
      return
    }

    // clear `tests` whenever we navigate to a new page. We want to avoid the following:
    //
    // * navigate to page A
    //   * tests[A] = v1
    // * navigate to page B
    //   * tests[B] = v2
    // * navigate back to page A
    //   * tests[A] = v1 + v1
    //
    // where the data in tests[A] gets doubled because we sent multiple e.g. ADD_REPORTS events,
    // where the backend re-sent the entire reports list under the assumption this was a fresh
    // page load, but the frontend simply appends them and duplicates the data.
    tests.clear()
    setLoadingStatus({
      count_tests: null,
      count_tests_loaded: null,
    })

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
                  failures: testData.failures,
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

            dispatch({
              type: DashboardEventType.TEST_LOAD_FINISHED,
              nodeid: nodeid,
            })
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
              type: DashboardEventType.ADD_OBSERVATIONS,
              nodeid: nodeid,
              observation_type: "rolling",
              observations: test.rolling.map(Observation.fromJson),
            })
            dispatch({
              type: DashboardEventType.ADD_OBSERVATIONS,
              nodeid: nodeid,
              observation_type: "corpus",
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
      const data = JSON.parse(event.data)
      const type = Number(data.type)
      const count_tests = Number(data.count_tests)
      const count_tests_loaded = Number(data.count_tests_loaded)

      switch (type) {
        case DashboardEventType.SET_STATUS: {
          const loading_status = {
            count_tests: count_tests,
            count_tests_loaded: count_tests_loaded,
          }
          setLoadingStatus(loading_status)

          dispatch({
            type: DashboardEventType.SET_STATUS,
            loading_status: loading_status,
          })

          if (count_tests_loaded === count_tests) {
            if (statusNotification.current !== null) {
              dismissNotification(statusNotification.current)
              statusNotification.current = null
            }
            break
          }

          const progressContent = React.createElement(ProgressBar, {
            current: count_tests_loaded,
            total: count_tests,
            message: `Note: dashboard is still starting up (${count_tests_loaded}/${count_tests} tests loaded)`,
          })

          if (!statusNotification.current) {
            statusNotification.current = addNotification(progressContent, null)
          } else {
            updateNotification(statusNotification.current, progressContent, null)
          }

          break
        }

        case DashboardEventType.ADD_TESTS: {
          dispatch({
            type: DashboardEventType.ADD_TESTS,
            tests: data.tests.map((test: any) => ({
              database_key: test.database_key,
              nodeid: test.nodeid,
              failures: new Map(
                Object.entries(test.failures).map(([key, value]) => [
                  key,
                  Failure.fromJson(value),
                ]),
              ),
            })),
          })
          break
        }

        case DashboardEventType.ADD_REPORTS: {
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

        case DashboardEventType.ADD_OBSERVATIONS: {
          dispatch({
            type: DashboardEventType.ADD_OBSERVATIONS,
            nodeid: data.nodeid,
            observation_type: data.observation_type,
            observations: data.observations.map(Observation.fromJson),
          })
          break
        }

        case DashboardEventType.ADD_FAILURES: {
          dispatch({
            type: DashboardEventType.ADD_FAILURES,
            nodeid: data.nodeid,
            failures: new Map(
              Object.entries(data.failures).map(([key, value]) => [
                key,
                Failure.fromJson(value),
              ]),
            ),
          })
          break
        }

        case DashboardEventType.TEST_LOAD_FINISHED: {
          dispatch({
            type: DashboardEventType.TEST_LOAD_FINISHED,
            nodeid: data.nodeid,
          })
          break
        }

        default:
          throw new Error(`Unknown event type: ${data.type}`)
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
    <DataContext.Provider value={{ tests, socket, doLoadData, testsLoaded }}>
      {children}
    </DataContext.Provider>
  )
}

export function useData(nodeid: string | null = null) {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error("useData must be used within a DataProvider")
  }

  useEffect(() => {
    context.doLoadData(nodeid)
  }, [nodeid, context.doLoadData])

  return context
}
