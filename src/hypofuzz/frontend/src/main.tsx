import React from "react"
import ReactDOM from "react-dom/client"
import { App } from "./App"
import "./styles.scss"
// ensure our array prototype definitions get loaded
import "./utils/prototypes"

ReactDOM.createRoot(document.getElementById("app")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
