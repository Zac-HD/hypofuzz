import hljs from "highlight.js/lib/core"

// a small taste of home in this wild land
export function sum(values: Iterable<number>, start: number = 0): number {
  return Array.from(values).reduce((total, val) => total + val, start)
}

export function reHighlight(
  containerRef: React.RefObject<HTMLElement | null>,
  force: boolean = false,
) {
  if (!containerRef.current) {
    return
  }

  if (force) {
    containerRef.current.querySelectorAll("code").forEach(element => {
      element.removeAttribute("data-highlighted")
    })
  }

  containerRef.current
    .querySelectorAll("code:not([data-highlighted='yes'])")
    .forEach(element => {
      hljs.highlightElement(element as HTMLElement)
    })
}

export function max<T>(array: T[], key: (value: T) => number): T | null
export function max(array: number[]): number | null
export function max<T>(
  array: T[] | number[],
  key?: (value: T) => number,
): T | number | null {
  if (key) {
    let maxElement: T | null = null
    let maxValue: number | null = null

    for (let i = 0; i < array.length; i++) {
      const element = array[i] as T
      const value = key(element)

      if (value != null && (maxValue === null || value > maxValue)) {
        maxValue = value
        maxElement = element
      }
    }

    return maxElement
  } else {
    let maxValue: number | null = null

    for (let i = 0; i < array.length; i++) {
      const value = array[i] as number

      if (value != null && (maxValue === null || value > maxValue)) {
        maxValue = value
      }
    }

    return maxValue
  }
}

export function min<T>(array: T[], key: (value: T) => number): T | null
export function min(array: number[]): number | null
export function min<T>(
  array: T[] | number[],
  key?: (value: T) => number,
): T | number | null {
  if (key) {
    let minElement: T | null = null
    let minValue: number | null = null

    for (let i = 0; i < array.length; i++) {
      const element = array[i] as T
      const value = key(element)

      if (value != null && (minValue === null || value < minValue)) {
        minValue = value
        minElement = element
      }
    }

    return minElement
  } else {
    let minValue: number | null = null

    for (let i = 0; i < array.length; i++) {
      const value = array[i] as number

      if (value != null && (minValue === null || value < minValue)) {
        minValue = value
      }
    }

    return minValue
  }
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

export function navigateOnClick(
  event: MouseEvent | React.MouseEvent,
  url: string,
  navigate: (path: string) => void,
): void {
  // support cmd for onclick
  if (event.metaKey || event.ctrlKey) {
    // ideally react router would have a utility to resolve a path to the
    // url that the router would navgiate to for that path. useHref does the
    // trick, but that's a hook, which restricts where it can be used.
    //
    // It's not worth spending more time trying to figure this out when hardcoding
    // works well.
    const usingHashRouter = import.meta.env.VITE_ROUTER_TYPE === "hash"
    const location = window.location
    const resolvedUrl = usingHashRouter
      ? `${location.origin}${location.pathname}#${url}`
      : `${location.origin}${url}`

    console.log(location.origin, location.pathname, url, resolvedUrl)
    window.open(resolvedUrl, "_blank")
  } else {
    navigate(url)
  }
}

export function readableNodeid(nodeid: string): string {
  return nodeid.split("::").pop() || nodeid
}
