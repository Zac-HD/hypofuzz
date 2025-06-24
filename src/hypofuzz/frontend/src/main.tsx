import "src/styles/styles.scss"
// ensure our array prototype definitions get loaded
import "src/utils/prototypes"

import React from "react"
import ReactDOM from "react-dom/client"
import { App } from "src/App"

ReactDOM.createRoot(document.getElementById("app")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
