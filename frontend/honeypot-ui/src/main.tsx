/**
 * src/main.tsx — React entry point for the Honeypot UI.
 *
 * Adds a global keyframe for the spinner animation (cannot be done
 * inline with React.CSSProperties) then mounts the App.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// Inject the @keyframes spin rule once at startup
const style = document.createElement('style')
style.textContent = `
  @keyframes spin { to { transform: rotate(360deg); } }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; }
`
document.head.appendChild(style)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
