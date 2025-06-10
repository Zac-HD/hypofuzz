import { createContext, ReactNode, useContext, useState } from "react"

import { Observation } from "../types/dashboard"

export type ObservationCategory = "covering" | "rolling"

export class Filter {
  createdAt: number

  constructor(
    public readonly name: string,
    public readonly predicate: (observation: Observation) => boolean,
    public readonly component: string,
    public readonly extraData?: any,
  ) {
    this.createdAt = Date.now()
  }
}

interface FilterContextType {
  filters: Map<string, Filter[]>
  setFilters: (filters: Map<string, Filter[]>) => void
  removeFilter: (component: string, name: string) => void
  observationCategory: ObservationCategory
  setObservationCategory: (observationCategory: ObservationCategory) => void
}

const FilterContext = createContext<FilterContextType | undefined>(undefined)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filtersByObsType, setFiltersByCategory] = useState<
    Map<ObservationCategory, Map<string, Filter[]>>
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
  const setFilters = (newFilters: Map<string, Filter[]>) => {
    setFiltersByCategory(prev => {
      const newMap = new Map(prev)
      newMap.set(observationCategory, newFilters)
      return newMap
    })
  }

  const removeFilter = (component: string, name: string) => {
    const newFilters = new Map(filters)
    const componentFilters = newFilters.get(component) || []
    const filteredFilters = componentFilters.filter(f => f.name !== name)

    if (filteredFilters.length === 0) {
      newFilters.delete(component)
    } else {
      newFilters.set(component, filteredFilters)
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
