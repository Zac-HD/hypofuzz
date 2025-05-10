// a small taste of home in this wild land
export function sum(values: Iterable<number>, start: number = 0): number {
  return Array.from(values).reduce((total, val) => total + val, start)
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
