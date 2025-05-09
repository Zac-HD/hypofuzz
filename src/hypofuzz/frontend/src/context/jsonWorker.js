import JSON5 from "json5"

self.onmessage = e => {
  const data = JSON5.parse(e.data)
  self.postMessage(data)
}
