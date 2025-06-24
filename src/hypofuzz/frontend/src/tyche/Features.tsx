import { NominalChart } from "src/tyche/NominalChart"
import { TycheSection } from "src/tyche/TycheSection"
import { Observation } from "src/types/dashboard"

export function Features({
  observations,
}: {
  observations: { raw: Observation[]; filtered: Observation[] }
}) {
  const features = new Set<string>()

  observations.raw.forEach(obs => {
    for (const key of obs.features.keys()) {
      if (key.startsWith("Retried draw from")) {
        continue
      }
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
