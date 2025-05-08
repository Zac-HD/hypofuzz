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
