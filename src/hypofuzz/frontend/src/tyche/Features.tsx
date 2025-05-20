import { Observation } from "../types/dashboard"
import { NominalChart } from "./NominalChart"

export function Features({ observations }: { observations: Observation[] }) {
  const features = new Set<string>()

  observations.forEach(obs => {
    for (const key of obs.features.keys()) {
      features.add(key)
    }
  })

  if (features.size === 0) {
    return null
  }

  return (
    <div className="card">
      <div className="tyche__section__header">
        <div className="tyche__section__title">Features</div>
      </div>
      {/* sort for stable display order */}
      {Array.from(features)
        .sort()
        .map(feature => (
          <NominalChart feature={feature} observations={observations} />
        ))}
    </div>
  )
}
