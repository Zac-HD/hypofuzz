// prefer loading api responses from dashboard_state.json, and ask the api otherwise
export async function fetchData<T>(endpoint: string): Promise<T | null> {
  try {
    const response = await fetch(
      new URL(/* @vite-ignore */ "dashboard_state/api.json", import.meta.url),
    )
    const data = JSON.parse(await response.text())
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
