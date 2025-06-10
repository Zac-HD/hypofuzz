import "./styles.scss"
// ensure our array prototype definitions get loaded
import "./utils/prototypes"

import React from "react"
import ReactDOM from "react-dom/client"

import { App } from "./App"

ReactDOM.createRoot(document.getElementById("app")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
