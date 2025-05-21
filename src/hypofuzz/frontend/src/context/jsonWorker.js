self.onmessage = e => {
  const data = JSON.parse(e.data)
  self.postMessage(data)
}
