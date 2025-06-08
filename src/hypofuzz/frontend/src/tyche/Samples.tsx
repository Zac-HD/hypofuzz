import { Observation } from "../types/dashboard"
import { MosaicChart } from "./MosaicChart"
import { TYCHE_COLOR } from "./Tyche"
import { TycheSection } from "./TycheSection"

export function Samples({
  observations,
}: {
  observations: { raw: Observation[]; filtered: Observation[] }
}) {
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
        name="samples"
        observations={observations}
        verticalAxis={[
          ["Passed", obs => obs.status === "passed"],
          ["Invalid", obs => obs.status === "gave_up"],
        ]}
        horizontalAxis={[
          ["Unique", obs => obs.isUnique ?? false],
          ["Duplicate", obs => obs.isDuplicate ?? false],
        ]}
        cssStyle={cellStyle}
      />
    </TycheSection>
  )
}
