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
        <div className="header-mark">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.55" />
            <path d="M12 3.5 L14.6 12 L12 20.5 L9.4 12 Z" fill="currentColor" />
          </svg>
          <h1>Autonomous Boat</h1>
        </div>
        <div className="header-status">
          {mission?.running && (
            <span className="mission-banner">
              {mission.name} — WP {mission.current_wp + 1}/{mission.total_wps} {mission.phase}
            </span>
          )}
          {network && (
            <span
              className={`net-badge net-badge--${network.active_kind}`}
              title={network.active_interface || ''}
            >
              {network.active_kind === 'wifi' && '📶 WiFi'}
              {network.active_kind === 'cellular' && '📡 4G'}
              {network.active_kind === 'offline' && '⚠ Offline'}
              {network.active_kind === 'other' && network.active_kind}
              {network.online ? '' : ' (no cloud)'}
            </span>
          )}
          <span className="conn-indicator">
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
        <div className="card panel-fill">
          <div className="card-header card-header--nav">Sensors</div>
          <SensorChart telemetry={telemetry} environment={environment} />
        </div>
        <div className="card panel-fill">
          <div className="card-header card-header--sensor">Camera</div>
          <CameraFeed />
        </div>
      </div>
    </div>
  )
}
