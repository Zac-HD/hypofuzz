export async function fetchData<T>(endpoint: string): Promise<T | null> {
  if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
    const response = await fetch(
      new URL(/* @vite-ignore */ "dashboard_state/api.json", import.meta.url),
    )
    return await response.json()
  }

  try {
    const response = await fetch(`/api/${endpoint}`)
    return await response.json()
  } catch (e) {
    console.error(`Failed to fetch /api/${endpoint}`, e)
    return null
  }
}

export async function fetchPatches<T>(nodeid: string): Promise<T | null> {
  const data = await fetchData<T>(`patches/${nodeid}`)
  if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
    return (data as any)?.patches?.[nodeid]
  }
  return data
}

export async function fetchAvailablePatches(): Promise<string[] | null> {
  const data = await fetchData<string[]>(`available_patches/`)
  if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
    return (data as any)?.available_patches
  }
  return data
}
