// a small taste of home in this wild land
export function sum(values: Iterable<number>): number {
  return Array.from(values).reduce((total, val) => total + val, 0)
}
