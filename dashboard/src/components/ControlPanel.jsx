import { useState } from 'react'

export default function ControlPanel({ api, mission, waypoints, onClearWaypoints }) {
  const [status, setStatus] = useState('')

  async function exec(action, name) {
    try {
      setStatus(`${name}...`)
      await action()
      setStatus(`${name} OK`)
      setTimeout(() => setStatus(''), 2000)
    } catch (e) {
      setStatus(`${name} FAILED: ${e.message}`)
    }
  }

  const running = mission?.running
  const paused = mission?.paused

  return (
    <div className="card">
      <div className="card-header">Controls</div>
      <div className="card-body">
        {/* Emergency */}
        <div className="btn-group" style={{ marginBottom: 8 }}>
          <button className="btn btn-danger" onClick={() => exec(api.estop, 'ESTOP')}>
            ESTOP
          </button>
          <button className="btn" onClick={() => exec(api.resumeEstop, 'Resume')}>
            Resume
          </button>
          <button className="btn btn-accent" onClick={() => exec(api.returnHome, 'RTH')}>
            RTH
          </button>
        </div>

        {/* Mission */}
        <div className="btn-group" style={{ marginBottom: 8 }}>
          {!running && waypoints?.length > 0 && (
            <button className="btn btn-success" onClick={() => {
              const m = { name: 'Dashboard Mission', waypoints }
              exec(() => api.uploadAndStart(m), 'Start Mission')
              onClearWaypoints?.()
            }}>
              Start ({waypoints.length} WPs)
            </button>
          )}
          {running && !paused && (
            <button className="btn" onClick={() => exec(api.pauseMission, 'Pause')}>
              Pause
            </button>
          )}
          {running && paused && (
            <button className="btn btn-accent" onClick={() => exec(api.resumeMission, 'Resume')}>
              Resume
            </button>
          )}
          {running && (
            <button className="btn btn-danger" onClick={() => exec(api.abortMission, 'Abort')}>
              Abort
            </button>
          )}
        </div>

        {/* Mission state */}
        {running && (
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
            WP {mission.current_wp + 1}/{mission.total_wps} — {mission.phase}
            {mission.est_depth_m > 0 && ` — ${mission.est_depth_m.toFixed(1)}m`}
            {mission.sample_count > 0 && ` — ${mission.sample_count} samples`}
          </div>
        )}

        {/* Planned waypoints */}
        {waypoints?.length > 0 && !running && (
          <div style={{ marginTop: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                PLANNED ({waypoints.length})
              </span>
              <button
                className="btn"
                style={{ padding: '2px 8px', fontSize: 10 }}
                onClick={onClearWaypoints}
              >
                Clear
              </button>
            </div>
            <ul className="wp-list">
              {waypoints.map((wp, i) => (
                <li key={i} className="wp-item">
                  <span>
                    <span className={`wp-type ${wp.type}`}>{wp.type === 'data' ? 'D' : 'P'}</span>
                    {' '}{wp.lat.toFixed(5)}, {wp.lon.toFixed(5)}
                  </span>
                  <span style={{ color: 'var(--text-dim)' }}>{wp.label || `WP${i}`}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Status */}
        {status && (
          <div style={{
            marginTop: 8, fontSize: 11, padding: '4px 8px',
            background: status.includes('FAIL') ? 'var(--danger-dim)' : 'rgba(56,189,248,0.1)',
            borderRadius: 4,
            color: status.includes('FAIL') ? 'var(--danger)' : 'var(--accent)',
          }}>
            {status}
          </div>
        )}

        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-dim)' }}>
          Click map to place waypoints
        </div>
      </div>
    </div>
  )
}
