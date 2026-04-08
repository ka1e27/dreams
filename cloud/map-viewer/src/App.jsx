import { useState, useEffect, useCallback } from 'react'
import HeatMap from './components/HeatMap'

const API_KEY = localStorage.getItem('cloud_api_key') || ''

async function apiFetch(path) {
  const headers = {}
  if (API_KEY) headers['X-API-Key'] = API_KEY
  const res = await fetch(path, { headers })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

export default function App() {
  const [missions, setMissions] = useState([])
  const [selectedMission, setSelectedMission] = useState('')
  const [sensorType, setSensorType] = useState('salinity_ec')
  const [readings, setReadings] = useState([])
  const [track, setTrack] = useState([])
  const [loading, setLoading] = useState(false)

  // Load missions on mount
  useEffect(() => {
    apiFetch('/api/v1/missions')
      .then(setMissions)
      .catch(e => console.error('Failed to load missions:', e))
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      // Load readings for full extent
      const r = await apiFetch(
        '/api/v1/readings?min_lat=-90&max_lat=90&min_lon=-180&max_lon=180&limit=10000'
      )
      setReadings(r)

      // Load track if mission selected
      if (selectedMission) {
        const t = await apiFetch(
          `/api/v1/track?mission_name=${encodeURIComponent(selectedMission)}&limit=50000`
        )
        setTrack(t)
      } else {
        setTrack([])
      }
    } catch (e) {
      console.error('Failed to load data:', e)
    }
    setLoading(false)
  }, [selectedMission])

  useEffect(() => { loadData() }, [loadData])

  return (
    <div className="viewer">
      <header className="header">
        <h1>Survey Data</h1>
        <div className="legend">
          <div className="legend-item">
            <div className="legend-dot" style={{ background: '#22c55e' }}></div>Low
          </div>
          <div className="legend-item">
            <div className="legend-dot" style={{ background: '#f59e0b' }}></div>Med
          </div>
          <div className="legend-item">
            <div className="legend-dot" style={{ background: '#ef4444' }}></div>High
          </div>
          {loading && <span style={{ color: 'var(--accent)', fontSize: 11 }}>Loading...</span>}
        </div>
      </header>

      <div className="panel">
        <div>
          <label>Sensor</label>
          <select value={sensorType} onChange={e => setSensorType(e.target.value)}>
            <option value="salinity_ec">Salinity (EC µS/cm)</option>
            <option value="water_temp">Water Temp (°C)</option>
            <option value="light_pct">Light (%)</option>
            <option value="depth_m">Depth (m)</option>
          </select>
        </div>

        <div>
          <label>Mission</label>
          <select value={selectedMission} onChange={e => setSelectedMission(e.target.value)}>
            <option value="">All missions</option>
            {missions.map(m => (
              <option key={m.mission_name} value={m.mission_name}>
                {m.mission_name} ({m.reading_count} readings)
              </option>
            ))}
          </select>
        </div>

        <button className="btn" onClick={loadData}>Refresh</button>

        <div style={{ fontSize: 11, color: 'var(--dim)' }}>
          {readings.length} readings loaded
          {track.length > 0 && `, ${track.length} track points`}
        </div>
      </div>

      <div className="map-area">
        <HeatMap
          readings={readings}
          track={track}
          sensorType={sensorType}
          selectedMission={selectedMission}
        />
      </div>
    </div>
  )
}
