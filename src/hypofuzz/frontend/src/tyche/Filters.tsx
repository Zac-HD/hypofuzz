import { faXmark } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"

import { useFilters } from "./FilterContext"

export function Filters() {
  const { filters, removeFilter } = useFilters()

  const allFilters = Array.from(filters.values())
    .flat()
    .sortKey(filter => filter.createdAt)

  if (allFilters.length === 0) {
    return null
  }

  return (
    <div className="tyche__filters">
      <div className="tyche__filters__title">Current Filters</div>
      {allFilters.map(filter => (
        <div
          key={`${filter.component}-${filter.name}`}
          className="tyche__filters__filter"
        >
          <div className="tyche__filters__filter__component">
            <div
              className="tyche__filters__filter__remove"
              onClick={() => removeFilter(filter.component, filter.name)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </div>
            {filter.component}
          </div>
          <div className="tyche__filters__filter__name">{filter.name}</div>
        </div>
      ))}
    </div>
  )
}
