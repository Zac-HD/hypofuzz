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

// Dedicated container for text measurement - created once and reused
let measureContainer: HTMLElement | null = null

function getMeasureContainer(): HTMLElement {
  if (!measureContainer) {
    measureContainer = document.createElement("div")
    measureContainer.style.cssText = `
      position: absolute;
      visibility: hidden;
      white-space: nowrap;
      top: -9999px;
      left: -9999px;
      pointer-events: none;
      z-index: -1;
    `
    document.body.appendChild(measureContainer)
  }
  return measureContainer
}

export function measureText(
  text: string,
  className: string = "",
): { width: number; height: number } {
  const container = getMeasureContainer()

  // reset to passed values
  container.className = className
  container.textContent = text

  const rect = container.getBoundingClientRect()
  return { width: rect.width, height: rect.height }
}
