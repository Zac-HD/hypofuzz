import { createContext, useContext, useState, ReactNode } from "react"
import { Observation } from "../types/dashboard"

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
}

const FilterContext = createContext<FilterContextType | undefined>(undefined)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Map<string, Filter[]>>(new Map())

  const removeFilter = (component: string, name: string) => {
    setFilters(prev => {
      const newMap = new Map(prev)
      const componentFilters = newMap.get(component) || []
      const filteredFilters = componentFilters.filter(f => f.name !== name)

      if (filteredFilters.length === 0) {
        newMap.delete(component)
      } else {
        newMap.set(component, filteredFilters)
      }

      return newMap
    })
  }

  const value: FilterContextType = {
    filters,
    setFilters,
    removeFilter,
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
