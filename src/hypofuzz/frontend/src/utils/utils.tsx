// a small taste of home in this wild land
export function sum(values: Iterable<number>, start: number = 0): number {
  return Array.from(values).reduce((total, val) => total + val, start)
}

export function max<T>(array: T[], key?: (value: T) => number): number | null {
  let maxValue: number | null = null

  for (let i = 0; i < array.length; i++) {
    const element = array[i]
    const value = key ? key(element) : (element as number)

    if (value != null && (maxValue === null || value > maxValue)) {
      maxValue = value
    }
  }

  return maxValue
}

export function mapsEqual(m1: Map<any, any>, m2: Map<any, any>): boolean {
  return (
    m1.size === m2.size &&
    Array.from(m1.keys()).every(key => m1.get(key) === m2.get(key))
  )
}

export function setsEqual(s1: Set<any>, s2: Set<any>): boolean {
  return s1.size === s2.size && Array.from(s1).every(key => s2.has(key))
}

// https://github.com/d3/d3-array/blob/be0ae0d2b36ab91b833294ad2cfc5d5905acbd0f/src/bisector.js#L22
export function bisectLeft(arr: any[], x: number, key?: (x: any) => number): number {
  let low = 0
  let high = arr.length
  while (low < high) {
    const mid = (low + high) >>> 1
    if (key ? key(arr[mid]) < x : arr[mid] < x) {
      low = mid + 1
    } else {
      high = mid
    }
  }
  return low
}

export function bisectRight(arr: any[], x: number, key?: (x: any) => number): number {
  let low = 0
  let high = arr.length
  while (low < high) {
    const mid = (low + high) >>> 1
    if (key ? key(arr[mid]) <= x : arr[mid] <= x) {
      low = mid + 1
    } else {
      high = mid
    }
  }
  return low
}

export function measureText(
  text: string,
  className: string = "",
): { width: number; height: number } {
  const element = document.createElement("div")
  element.className = className
  element.style.visibility = "hidden"
  element.style.position = "absolute"
  element.style.whiteSpace = "nowrap"
  element.textContent = text

  document.body.appendChild(element)
  const rect = element.getBoundingClientRect()
  document.body.removeChild(element)

  return { width: rect.width, height: rect.height }
}
