import { Observation } from "../types/dashboard"
import { MosaicChart } from "./MosaicChart"
import { TYCHE_COLOR } from "./Tyche"

export function Samples({ observations }: { observations: Observation[] }) {
  function isPassed(observation: Observation) {
    return observation.status === "passed"
  }
  function isInvalid(observation: Observation) {
    return observation.status === "gave_up"
  }

  // map of each representation to an arbitrary observation index which we declare as the
  // unique observation for that representation.
  const uniqueReprIndex = new Map<string, number>()
  for (const [index, observation] of observations.entries()) {
    uniqueReprIndex.set(observation.representation, index)
  }

  function isUnique(observation: Observation) {
    return (
      observations.indexOf(observation) ===
      uniqueReprIndex.get(observation.representation)
    )
  }
  function isDuplicate(observation: Observation) {
    return (
      observations.indexOf(observation) !==
      uniqueReprIndex.get(observation.representation)
    )
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
    <MosaicChart
      title="Sample breakdown"
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
  )
}
