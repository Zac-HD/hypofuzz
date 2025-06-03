import { useState } from "react"
import { Test } from "../types/dashboard"
import { Toggle } from "../components/Toggle"
import { Features } from "./Features"
import { Samples } from "./Samples"
import { Representation } from "./Representation"

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

  if (!test.observations_loaded) {
    return (
      <div className="card">
        <div className="card__header">Loading observations...</div>
      </div>
    )
  }

  const observations =
    observationType === "rolling"
      ? // newest first for rolling observations
        test.rolling_observations.sortKey(observation => -observation.run_start)
      : test.corpus_observations

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
            { value: "covering", label: "Covering" },
            { value: "rolling", label: "Rolling" },
          ]}
        />
      </div>
      {observations.length > 0 ? (
        <>
          <Samples observations={observations} />
          <Features observations={observations} />
          <Representation
            observations={observations}
            observationType={observationType}
          />
        </>
      ) : (
        <div className="tyche__section">No observations</div>
      )}
    </div>
  )
}
