export async function fetchData<T>(endpoint: string): Promise<T | null> {
  if (import.meta.env.VITE_USE_DASHBOARD_STATE === "1") {
    const response = await fetch(
      new URL(/* @vite-ignore */ "dashboard_state/api.json", import.meta.url),
    )
    const data = await response.json()
    const params = endpoint.split("/", 1)
    let result = data
    for (const param of params) {
      if (param === "") {
        break
      }
      console.assert(
        Object.keys(result).includes(param),
        `result=${JSON.stringify(result)}, params=${param}, param=${params}`,
      )
      result = result[param]
    }
    return result
  }

  try {
    const response = await fetch(`/api/${endpoint}`)
    return await response.json()
  } catch (e) {
    console.error(`Failed to fetch /api/${endpoint}`, e)
    return null
  }
}
