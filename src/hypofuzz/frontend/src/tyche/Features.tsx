import { Observation } from "../types/dashboard"
import { NominalChart } from "./NominalChart"
import { TycheSection } from "./TycheSection"

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
    <TycheSection title="Features">
      {/* sort for stable display order */}
      {Array.from(features)
        .sort()
        .map(feature => (
          <NominalChart feature={feature} observations={observations} />
        ))}
    </TycheSection>
  )
}
