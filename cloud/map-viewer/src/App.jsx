import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import HeatMap, { HEAT_SCALE } from './components/HeatMap'

// Units are cosmetic (legend text only) — the underlying field names and values
// read from the API are untouched.
const SENSOR_UNITS = {
  salinity_ec: 'µS/cm',
  water_temp: '°C',
  light_pct: '%',
  depth_m: 'm',
}

async function apiFetch(path, signal) {
  // Read the key fresh on every call (not a value frozen at module load) so a
  // key saved via the UI takes effect immediately, with no page reload needed.
  const apiKey = localStorage.getItem('cloud_api_key') || ''
  const headers = {}
  if (apiKey) headers['X-API-Key'] = apiKey
  const res = await fetch(path, { headers, signal })
  if (!res.ok) {
    const err = new Error(`Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.json()
}

function describeError(e) {
  if (e?.status === 401 || e?.status === 403) {
    return { kind: 'auth', message: 'The cloud API rejected the request — missing or invalid API key.' }
  }
  return { kind: 'generic', message: 'Could not reach the survey data API. Check your connection and retry.' }
}

function sensorValue(reading, sensorType) {
  const v = reading[sensorType]
  return v !== null && v !== undefined ? v : 0
}

function formatMissionMeta(m) {
  const count = `${m.reading_count} reading${m.reading_count === 1 ? '' : 's'}`
  if (!m.last_reading) return count
  const d = new Date(m.last_reading)
  return Number.isNaN(d.getTime()) ? count : `${count} · ${d.toLocaleDateString()}`
}

export default function App() {
  const [missions, setMissions] = useState([])
  const [selectedMission, setSelectedMission] = useState('')
  const [sensorType, setSensorType] = useState('salinity_ec')
  const [readings, setReadings] = useState([])
  const [track, setTrack] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [apiKeyDraft, setApiKeyDraft] = useState(() => localStorage.getItem('cloud_api_key') || '')

  // Each in-flight request family gets its own AbortController so a fast
  // mission switch (or a second Refresh click) cancels the stale request
  // instead of racing it — without cancellation, an old, slower response
  // could resolve after a newer one and clobber state with stale data.
  const missionsAbortRef = useRef(null)
  const readingsAbortRef = useRef(null)
  const trackAbortRef = useRef(null)

  const loadMissions = useCallback(async () => {
    missionsAbortRef.current?.abort()
    const controller = new AbortController()
    missionsAbortRef.current = controller
    try {
      const m = await apiFetch('/api/v1/missions', controller.signal)
      setMissions(m)
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.error('Failed to load missions:', e)
        setError(describeError(e))
      }
    }
  }, [])

  // Full-extent readings load. Deliberately has no dependency on the selected
  // mission — mission filtering happens client-side in HeatMap, so switching
  // missions must not re-fetch the entire readings set from the server.
  const loadReadings = useCallback(async () => {
    readingsAbortRef.current?.abort()
    const controller = new AbortController()
    readingsAbortRef.current = controller
    setLoading(true)
    try {
      const r = await apiFetch(
        '/api/v1/readings?min_lat=-90&max_lat=90&min_lon=-180&max_lon=180&limit=10000',
        controller.signal
      )
      setReadings(r)
      setError(null)
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.error('Failed to load readings:', e)
        setError(describeError(e))
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  const loadTrack = useCallback(async missionName => {
    trackAbortRef.current?.abort()
    if (!missionName) {
      setTrack([])
      return
    }
    const controller = new AbortController()
    trackAbortRef.current = controller
    try {
      const t = await apiFetch(
        `/api/v1/track?mission_name=${encodeURIComponent(missionName)}&limit=50000`,
        controller.signal
      )
      setTrack(t)
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.error('Failed to load track:', e)
        setError(describeError(e))
      }
    }
  }, [])

  // Mount: load missions + the full readings extent once.
  useEffect(() => {
    loadMissions()
    return () => missionsAbortRef.current?.abort()
  }, [loadMissions])

  useEffect(() => {
    loadReadings()
    return () => readingsAbortRef.current?.abort()
  }, [loadReadings])

  // Mission change: only the track needs to change; readings stay as-is.
  useEffect(() => {
    loadTrack(selectedMission)
    return () => trackAbortRef.current?.abort()
  }, [selectedMission, loadTrack])

  const refresh = useCallback(() => {
    loadReadings()
    loadTrack(selectedMission)
  }, [loadReadings, loadTrack, selectedMission])

  const saveApiKey = useCallback(e => {
    e.preventDefault()
    localStorage.setItem('cloud_api_key', apiKeyDraft.trim())
    setError(null)
    loadMissions()
    refresh()
  }, [apiKeyDraft, loadMissions, refresh])

  // Real min/max for the current sensor + mission filter, computed with the
  // exact same semantics HeatMap uses to color the points (missing values
  // default to 0) so the legend range always matches what's drawn on the map.
  const sensorRange = useMemo(() => {
    const source = selectedMission
      ? readings.filter(r => r.mission_name === selectedMission)
      : readings
    if (source.length === 0) return null
    let lo = Infinity
    let hi = -Infinity
    for (const r of source) {
      const v = sensorValue(r, sensorType)
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
    return { min: lo, max: hi }
  }, [readings, selectedMission, sensorType])

  const legendGradient = useMemo(
    () => `linear-gradient(90deg, ${HEAT_SCALE.map(s => `rgb(${s.color.join(',')}) ${s.stop * 100}%`).join(', ')})`,
    []
  )

  const unit = SENSOR_UNITS[sensorType] || ''
  const isEmpty = !loading && !error && readings.length === 0

  return (
    <div className="viewer">
      <header className="header">
        <div className="brand">
          <span className={`status-dot ${error ? 'status-dot--error' : 'status-dot--ok'}`} aria-hidden="true" />
          <h1>D.R.E.A.M.S <span className="brand-sub">Survey Data</span></h1>
        </div>

        <div className="legend" aria-label="Heatmap color scale">
          {sensorRange ? (
            <>
              <span className="legend-value">{sensorRange.min.toFixed(1)}{unit}</span>
              <div
                className="legend-bar"
                style={{ background: legendGradient }}
                role="img"
                aria-label={`Color scale from ${sensorRange.min.toFixed(1)} to ${sensorRange.max.toFixed(1)} ${unit}`.trim()}
              />
              <span className="legend-value">{sensorRange.max.toFixed(1)}{unit}</span>
            </>
          ) : (
            <span className="legend-value legend-value--dim">No data</span>
          )}
        </div>

        <div className="status-line" role="status" aria-live="polite">
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading && 'Loading…'}
        </div>
      </header>

      <div className="panel">
        <div>
          <label htmlFor="sensor-select">Sensor</label>
          <select id="sensor-select" value={sensorType} onChange={e => setSensorType(e.target.value)}>
            <option value="salinity_ec">Salinity (EC µS/cm)</option>
            <option value="water_temp">Water Temp (°C)</option>
            <option value="light_pct">Light (%)</option>
            <option value="depth_m">Depth (m)</option>
          </select>
        </div>

        <div>
          <label htmlFor="mission-select">Mission</label>
          <select id="mission-select" value={selectedMission} onChange={e => setSelectedMission(e.target.value)}>
            <option value="">All missions</option>
            {missions.map(m => (
              <option key={m.mission_name} value={m.mission_name}>
                {m.mission_name} ({formatMissionMeta(m)})
              </option>
            ))}
          </select>
        </div>

        <button className="btn" onClick={refresh} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>

        <div className="meta-line">
          {readings.length} reading{readings.length === 1 ? '' : 's'} loaded
          {track.length > 0 && `, ${track.length} track points`}
        </div>

        {error && (
          <div className={`banner banner--${error.kind === 'auth' ? 'warn' : 'error'}`} role="alert">
            <p>{error.message}</p>
            {error.kind === 'auth' && (
              <form className="key-form" onSubmit={saveApiKey}>
                <label htmlFor="api-key-input">Cloud API key</label>
                <input
                  id="api-key-input"
                  type="password"
                  autoComplete="off"
                  value={apiKeyDraft}
                  onChange={e => setApiKeyDraft(e.target.value)}
                  placeholder="X-API-Key"
                />
                <button type="submit" className="btn btn--sm">Save &amp; retry</button>
              </form>
            )}
          </div>
        )}
      </div>

      <div className="map-area">
        <HeatMap
          readings={readings}
          track={track}
          sensorType={sensorType}
          selectedMission={selectedMission}
        />
        {isEmpty && (
          <div className="empty-state" role="status">
            <p>No survey readings yet.</p>
            <p className="empty-state-hint">Once the boat uploads data, it will appear here automatically.</p>
          </div>
        )}
      </div>
    </div>
  )
}
