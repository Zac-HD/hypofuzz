// prefer loading api responses from dashboard_state.json, and ask the api otherwise
export async function fetchData<T>(endpoint: string): Promise<T | null> {
  try {
    const response = await fetch(
      new URL("dashboard_state.json", import.meta.url),
    )
    const data = await response.json()
    return data[endpoint]
  } catch (e) {
    try {
      const response = await fetch(`/api/${endpoint}/`)
      return await response.json()
    } catch (e) {
      console.error(`Failed to fetch ${endpoint}:`, e)
      return null
    }
  }
}
