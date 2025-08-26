import { test, assert } from "vitest"
import { formatNumber } from "../src/utils/testStats"

const cases: Array<[number, string]> = [
  [0, "0"],
  [1, "1"],
  [999, "999"],
  [2000, "2.0k"],
  [2300, "2.3k"],
  [-4200, "-4.2k"],
  [1500000, "1.5M"],
]

for (const [input, expected] of cases) {
  test(`formatNumber(${input})`, function () {
    assert.equal(formatNumber(input), expected)
  })
}
