export {}

declare global {
  interface Array<T> {
    /**
     * Similar to Array.sort, but uses a per-item key function, like python's list.sort(key=lambda x: x.id).
     */
    sortKey<K extends any[] | string | number>(key: (item: T) => K): T[]
  }
}

if (!Array.prototype.sortKey) {
  Array.prototype.sortKey = function <T, K extends any[] | string | number>(
    key: (item: T) => K,
  ): T[] {
    return this.sort((a, b) => {
      const keyA = key(a)
      const keyB = key(b)

      if (Array.isArray(keyA) && Array.isArray(keyB)) {
        for (let i = 0; i < Math.min(keyA.length, keyB.length); i++) {
          if (keyA[i] < keyB[i]) return -1
          if (keyA[i] > keyB[i]) return 1
        }
        return 0
      }
      if (keyA < keyB) return -1
      if (keyA > keyB) return 1
      return 0
    })
  }
}
