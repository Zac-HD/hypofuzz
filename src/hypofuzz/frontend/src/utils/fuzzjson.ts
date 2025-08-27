// must match python's hypofuzz.utils
const FUZZJSON_INF = "hypofuzz-inf-a928fa52b3ea4a9a"
const FUZZJSON_NINF = "hypofuzz-ninf-a928fa52b3ea4a9a"
const FUZZJSON_NAN = "hypofuzz-nan-a928fa52b3ea4a9a"

export function fuzzjsonReviver(_key: string, value: any): any {
  if (value === FUZZJSON_INF) return Infinity
  if (value === FUZZJSON_NINF) return -Infinity
  if (value === FUZZJSON_NAN) return NaN
  return value
}
