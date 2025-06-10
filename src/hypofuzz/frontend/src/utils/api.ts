export async function fetchData<T>(endpoint: string): Promise<T | null> {
  if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
    const response = await fetch(
      new URL(/* @vite-ignore */ "dashboard_state/api.json", import.meta.url),
    )
    const data = await response.json()
    return data[endpoint.replace(/\/$/, "")]
  }

  try {
    const response = await fetch(`/api/${endpoint}`)
    return await response.json()
  } catch (e) {
    console.error(`Failed to fetch /api/${endpoint}`, e)
    return null
  }
}
