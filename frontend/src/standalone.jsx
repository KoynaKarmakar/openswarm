// Standalone entry for the OpenSwarm canvas: renders ONLY the Swarm Console,
// no auth/login, with the swarm running client-side (window.__SWARM_MOCK__).
import React from 'react'
import ReactDOM from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import SwarmConsole from './pages/SwarmConsole'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <MemoryRouter>
      <SwarmConsole />
    </MemoryRouter>
  </React.StrictMode>
)
