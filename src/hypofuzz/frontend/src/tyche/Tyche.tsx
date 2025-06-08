import { useState, useEffect } from "react"
import { Test, Observation } from "../types/dashboard"
import { Toggle } from "../components/Toggle"
import { Features } from "./Features"
import { Samples } from "./Samples"
import { Representation } from "./Representation"
import { Set, List } from "immutable"

export enum TYCHE_COLOR {
  // https://github.com/tyche-pbt/tyche-extension/blob/main/webview-ui/src/utilities/colors.ts
  // plus a 10% blend of #ECEFF4 to soften them
  PRIMARY = "#6b8ab5",
  SUCCESS = "#8ba86b",
  WARNING = "#d59a7e",
  ERROR = "#c77a7e",
  ACCENT = "#c1a2bb",
  ACCENT2 = "#9fc7c6",
  ACCENT3 = "#edd39a",
  ACCENT4 = "#99c7d6",
  ACCENT5 = "#8faac6",
}

export function Tyche({ test }: { test: Test }) {
  const [observationType, setObservationType] = useState<"covering" | "rolling">(
    "covering",
  )
  const [selectedCells, setSelectedCells] = useState<Set<List<number>>>(Set())

  const observations =
    observationType === "rolling"
      ? // newest first for rolling observations
        test.rolling_observations.sortKey(observation => -observation.run_start)
      : test.corpus_observations

  const filteredObservations =
    selectedCells.size === 0
      ? observations
      : observations.filter(observation => {
          const verticalAxis: ((obs: Observation) => boolean)[] = [
            obs => obs.status === "passed",
            obs => obs.status === "gave_up",
          ]
          const horizontalAxis: ((obs: Observation) => boolean)[] = [
            obs => obs.isUnique ?? false,
            obs => obs.isDuplicate ?? false,
          ]
          return selectedCells.some(cellCoords => {
            const [rowIndex, colIndex] = cellCoords.toArray()
            const verticalPredicate = verticalAxis[rowIndex]
            const horizontalPredicate = horizontalAxis[colIndex]

            return verticalPredicate(observation) && horizontalPredicate(observation)
          })
        })

  return (
    <div className="card">
      <div className="card__header">
        <span>Observations</span>
      </div>
      <div
        style={{
          paddingTop: "10px",
          paddingBottom: "10px",
          display: "flex",
          justifyContent: "flex-start",
          fontSize: "1.05rem",
          fontWeight: "500",
        }}
      >
        <Toggle
          value={observationType}
          onChange={setObservationType}
          options={[
            { value: "covering", content: "Covering" },
            { value: "rolling", content: "Rolling" },
          ]}
        />
      </div>
      {observations.length > 0 ? (
        <>
          <Samples observations={observations} onSelection={setSelectedCells} />
          <Features observations={observations} />
          <Representation
            observations={filteredObservations}
            observationType={observationType}
          />
        </>
      ) : (
        <div className="tyche__section">No observations</div>
      )}
    </div>
  )
}
