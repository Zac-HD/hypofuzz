import { createContext, ReactNode, useContext, useState } from "react"
import { Observation } from "src/types/dashboard"

export type ObservationCategory = "covering" | "rolling"

export class Filter {
  createdAt: number

  constructor(
    // display value for the left half (key) of a "current filters" tag
    public readonly name: string,
    // display value for the right half (value) of a "current filters" tag
    public readonly valueName: string,
    public readonly predicate: (observation: Observation) => boolean,
    public readonly key: string,
    public readonly extraData?: any,
  ) {
    this.createdAt = Date.now()
  }
}

type Filters = Map<string, Filter[]>

interface FilterContextType {
  filters: Filters
  setFilters: (filters: Filters) => void
  removeFilter: (key: string) => void
  observationCategory: ObservationCategory
  setObservationCategory: (observationCategory: ObservationCategory) => void
}

const FilterContext = createContext<FilterContextType | undefined>(undefined)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filtersByObsType, setFiltersByKey] = useState<
    Map<ObservationCategory, Filters>
  >(
    new Map([
      ["covering", new Map()],
      ["rolling", new Map()],
    ]),
  )
  const [observationCategory, setObservationCategory] =
    useState<ObservationCategory>("covering")

  const filters =
    filtersByObsType.get(observationCategory) || new Map<string, Filter[]>()
  const setFilters = (newFilters: Filters) => {
    setFiltersByKey(prev => {
      const newMap = new Map(prev)
      newMap.set(observationCategory, newFilters)
      return newMap
    })
  }

  const removeFilter = (key: string) => {
    const newFilters = new Map(filters)
    const keyFilters = newFilters.get(key) || []
    const filteredFilters = keyFilters.filter(f => f.key !== key)

    if (filteredFilters.length === 0) {
      newFilters.delete(key)
    } else {
      newFilters.set(key, filteredFilters)
    }

    setFilters(newFilters)
  }

  const value: FilterContextType = {
    filters,
    setFilters,
    removeFilter,
    observationCategory,
    setObservationCategory,
  }

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>
}

export function useFilters() {
  const context = useContext(FilterContext)
  if (context === undefined) {
    throw new Error("useFilters must be used within a FilterProvider")
  }
  return context
}
