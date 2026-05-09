import { useState, useCallback } from 'react'
import { useTelemetry } from './hooks/useTelemetry'
import { useApi } from './hooks/useApi'
import { useNetwork } from './hooks/useNetwork'
import BoatMap from './components/BoatMap'
import TelemetryPanel from './components/TelemetryPanel'
import ControlPanel from './components/ControlPanel'
import SensorChart from './components/SensorChart'
import CameraFeed from './components/CameraFeed'

export default function App() {
  const { data, connected } = useTelemetry()
  const api = useApi()
  const network = useNetwork(api)
  const [waypoints, setWaypoints] = useState([])

  const handleMapClick = useCallback((lat, lon) => {
    setWaypoints(prev => [...prev, {
      lat: parseFloat(lat.toFixed(6)),
      lon: parseFloat(lon.toFixed(6)),
      type: 'data',
      max_time: 300,
      label: '',
    }])
  }, [])

  const clearWaypoints = useCallback(() => setWaypoints([]), [])

  const telemetry = data?.telemetry
  const environment = data?.environment
  const navigation = data?.navigation
  const mission = data?.mission
  const winchMode = data?.config?.winch_mode || 'survey'

  // Build waypoint list for map (planned + active mission)
  const mapWaypoints = mission?.running
    ? [] // Active mission WPs come from server, shown via mission state
    : waypoints

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="header">
        <h1>Autonomous Boat</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11 }}>
          {mission?.running && (
            <span style={{ color: 'var(--accent)' }}>
              {mission.name} — WP {mission.current_wp + 1}/{mission.total_wps} {mission.phase}
            </span>
          )}
          {network && (
            <span title={network.active_interface || ''}>
              {network.active_kind === 'wifi' && '📶 WiFi'}
              {network.active_kind === 'cellular' && '📡 4G'}
              {network.active_kind === 'offline' && '⚠ Offline'}
              {network.active_kind === 'other' && network.active_kind}
              {network.online ? '' : ' (no cloud)'}
            </span>
          )}
          <span>
            <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`}></span>
            {connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
      </header>

      {/* Map */}
      <div className="map-area">
        <BoatMap
          telemetry={telemetry}
          mission={mission}
          waypoints={mapWaypoints}
          onMapClick={handleMapClick}
        />
      </div>

      {/* Sidebar */}
      <div className="sidebar">
        <ControlPanel
          api={api}
          mission={mission}
          waypoints={waypoints}
          onClearWaypoints={clearWaypoints}
        />
        <TelemetryPanel
          telemetry={telemetry}
          environment={environment}
          navigation={navigation}
          connected={connected}
          winchMode={winchMode}
        />
      </div>

      {/* Bottom panel */}
      <div className="bottom-panel">
        <div style={{ background: 'var(--bg-card)' }}>
          <div className="card-header">Sensors</div>
          <SensorChart telemetry={telemetry} environment={environment} />
        </div>
        <div style={{ background: 'var(--bg-card)' }}>
          <div className="card-header">Camera</div>
          <CameraFeed />
        </div>
      </div>
    </div>
  )
}
