import { useState, useEffect } from "react"

export function usePreference<T>(
  key: string,
  defaultValue: T,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const saved = sessionStorage.getItem(key)
    if (saved === null) return defaultValue
    return JSON.parse(saved)
  })

  useEffect(() => {
    sessionStorage.setItem(key, JSON.stringify(value))
  }, [value, key])

  return [value, setValue]
}
