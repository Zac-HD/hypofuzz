import { faXmark } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { useFilters } from "src/tyche/FilterContext"

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
      <div className="tyche__filters__title">Filters</div>
      {allFilters.map(filter => (
        <div key={filter.key} className="tyche__filters__filter">
          <div className="tyche__filters__filter__name">
            <div
              className="tyche__filters__filter__remove"
              onClick={() => removeFilter(filter.key)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </div>
            {filter.name}
          </div>
          <div className="tyche__filters__filter__value-name">{filter.valueName}</div>
        </div>
      ))}
    </div>
  )
}
