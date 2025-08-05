import { ObservationCategory } from "src/tyche/FilterContext"
import { NominalChart, SystemFeature, UserFeature } from "src/tyche/NominalChart"
import { TycheSection } from "src/tyche/TycheSection"
import { Observation } from "src/types/dashboard"

// use a private name to avoid collisions with user features.
const STABILITY_FEATURE_KEY = "__hypofuzz_stability"

export function Features({
  observations,
  observationCategory,
}: {
  observations: { raw: Observation[]; filtered: Observation[] }
  observationCategory: ObservationCategory
}) {
  const featureNames = new Set<string>()

  observations.raw.forEach(obs => {
    for (const key of obs.features.keys()) {
      if (key.startsWith("Retried draw from")) {
        continue
      }
      featureNames.add(key)
    }
  })

  const features = Array.from(featureNames).map(
    feature => new UserFeature(feature, feature),
  )
  // we currently only add covering observations if they are stable, and don't re-check for
  // stability after. Skip here to avoid showing a boring graph full of "stable" for the
  // covering observation view.
  //
  // We should also enable this for covering if/when we have more interesting data to show.
  if (observationCategory == "rolling") {
    features.push(
      new SystemFeature(
        STABILITY_FEATURE_KEY,
        "Stability",
        observation => observation.stability ?? "unknown",
      ),
    )
  }

  if (features.length === 0) {
    return null
  }

  return (
    <TycheSection title="Features">
      {/* sort for stable display order */}
      {Array.from(features)
        .sortKey(feature => feature.name)
        .map(feature => (
          <NominalChart feature={feature} observations={observations} />
        ))}
    </TycheSection>
  )
}
