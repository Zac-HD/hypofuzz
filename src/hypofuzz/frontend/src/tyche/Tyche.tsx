import { Toggle } from "src/components/Toggle"
import { Features } from "src/tyche/Features"
import { FilterProvider, useFilters } from "src/tyche/FilterContext"
import { Filters } from "src/tyche/Filters"
import { Representation } from "src/tyche/Representation"
import { Samples } from "src/tyche/Samples"
import { Test } from "src/types/test"

export const PRESENT_STRING = "Present"
export const NOT_PRESENT_STRING = "Not present"

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

function TycheInner({ test }: { test: Test }) {
  const { filters, observationCategory, setObservationCategory } = useFilters()

  const rawObservations =
    observationCategory === "rolling"
      ? // newest first for rolling observations
        test.rolling_observations.sortKey(observation => -observation.run_start)
      : test.corpus_observations

  function filteredObservations() {
    const allFilters = Array.from(filters.values()).flat()

    if (allFilters.length === 0) {
      return rawObservations
    }

    return rawObservations.filter(observation => {
      return allFilters.every(filter => filter.predicate(observation))
    })
  }

  const observations = {
    raw: rawObservations,
    filtered: filteredObservations(),
  }

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
          fontSize: "1.05rem",
          fontWeight: "500",
        }}
      >
        <Toggle
          value={observationCategory}
          onChange={setObservationCategory}
          options={[
            { value: "covering", content: "Covering" },
            { value: "rolling", content: "Rolling" },
          ]}
        />
      </div>
      <Filters />
      {observations.raw.length > 0 ? (
        <>
          <Samples observations={observations} />
          <Features observations={observations} />
          <Representation
            observations={observations}
            observationCategory={observationCategory}
          />
        </>
      ) : (
        <div className="tyche__section">No observations</div>
      )}
    </div>
  )
}

export function Tyche({ test }: { test: Test }) {
  return (
    <FilterProvider>
      <TycheInner test={test} />
    </FilterProvider>
  )
}
