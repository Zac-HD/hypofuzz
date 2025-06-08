import { Observation } from "../types/dashboard"
import { MosaicChart } from "./MosaicChart"
import { TYCHE_COLOR } from "./Tyche"
import { TycheSection } from "./TycheSection"
import { useMemo } from "react"

export function Samples({ observations }: { observations: Observation[] }) {
  function isPassed(observation: Observation) {
    return observation.status === "passed"
  }
  function isInvalid(observation: Observation) {
    return observation.status === "gave_up"
  }

  const reprCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const observation of observations) {
      counts.set(
        observation.representation,
        (counts.get(observation.representation) || 0) + 1,
      )
    }
    return counts
  }, [observations])

  function isUnique(observation: Observation) {
    return reprCounts.get(observation.representation)! == 1
  }
  function isDuplicate(observation: Observation) {
    return reprCounts.get(observation.representation)! > 1
  }

  function cellStyle(row: string, column: string): React.CSSProperties {
    const style: React.CSSProperties = {}

    if (row === "Passed") {
      style.backgroundColor = TYCHE_COLOR.SUCCESS
    } else if (row === "Invalid") {
      style.backgroundColor = TYCHE_COLOR.WARNING
    } else if (row === "Failed") {
      style.backgroundColor = TYCHE_COLOR.ERROR
    }

    if (column === "Duplicate") {
      style.opacity = 0.7
    }

    return style
  }

  return (
    <TycheSection title="Sample breakdown">
      <MosaicChart
        observations={observations}
        verticalAxis={[
          ["Passed", isPassed],
          ["Invalid", isInvalid],
        ]}
        horizontalAxis={[
          ["Unique", isUnique],
          ["Duplicate", isDuplicate],
        ]}
        cssStyle={cellStyle}
      />
    </TycheSection>
  )
}
