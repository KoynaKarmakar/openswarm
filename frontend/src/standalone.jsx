// Standalone entry for the OpenSwarm canvas: a self-contained multi-tab agentic
// app — every tab runs the swarm engine live in the browser (no backend, no auth).
import React from 'react'
import ReactDOM from 'react-dom/client'
import StandaloneApp from './standalone/StandaloneApp'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <StandaloneApp />
  </React.StrictMode>
)
