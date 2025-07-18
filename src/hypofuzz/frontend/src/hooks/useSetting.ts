import { useEffect, useState } from "react"

const settingCallbacks = new Map<string, Set<(value: any) => void>>()

export function useSetting<T>(key: string, defaultValue: T): [T, (value: T) => void] {
  const [value, _setValue] = useState<T>(() => {
    // note: sessionStorage is per-tab. localStorage is per-browser-session.
    // we may want to add a param to use one or the other (with a fallback from
    // session to local storage?)
    const saved = sessionStorage.getItem(key)
    if (saved === null) return defaultValue
    return JSON.parse(saved)
  })

  useEffect(() => {
    if (!settingCallbacks.has(key)) {
      settingCallbacks.set(key, new Set())
    }
    settingCallbacks.get(key)!.add(_setValue)

    return () => {
      settingCallbacks.get(key)!.delete(_setValue)
    }
  }, [key])

  function setValue(newValue: T) {
    sessionStorage.setItem(key, JSON.stringify(newValue))
    // broadcast settings changes to other listeners. This way if there are two
    // useSetting call for the same setting key, changes in one get reflected in the other.
    settingCallbacks.get(key)!.forEach(callback => callback(newValue))
  }

  return [value, setValue]
}
