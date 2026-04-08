const HEALTH_LABELS = ['GPS', 'CMP', 'BAT', 'AIR', 'MOT', 'POD']

function healthClass(flag) {
  return flag === '1' ? 'ok' : 'fault'
}

function battClass(v) {
  if (v <= 13.6) return 'danger'
  if (v <= 14.0) return 'warn'
  return 'ok'
}

export default function TelemetryPanel({ telemetry, environment, navigation, connected }) {
  const t = telemetry || {}
  const e = environment || {}
  const n = navigation || {}

  return (
    <>
      {/* Connection */}
      <div className="card">
        <div className="card-header">Connection</div>
        <div className="card-body">
          <div className="data-row">
            <span className="data-label">Status</span>
            <span className="data-value">
              <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`}></span>
              {connected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="card">
        <div className="card-header">Navigation</div>
        <div className="card-body">
          <div className="data-row">
            <span className="data-label">Position</span>
            <span className="data-value accent">
              {(t.lat || 0).toFixed(6)}, {(t.lon || 0).toFixed(6)}
            </span>
          </div>
          <div className="data-row">
            <span className="data-label">Heading</span>
            <span className="data-value">{(t.heading || 0).toFixed(1)}°</span>
          </div>
          <div className="data-row">
            <span className="data-label">Speed</span>
            <span className="data-value">{(t.speed_knots || 0).toFixed(1)} kn</span>
          </div>
          {n.active && (
            <>
              <div className="data-row">
                <span className="data-label">To target</span>
                <span className="data-value accent">{(n.distance_m || 0).toFixed(1)} m</span>
              </div>
              <div className="data-row">
                <span className="data-label">Bearing</span>
                <span className="data-value">{(n.bearing_deg || 0).toFixed(1)}°</span>
              </div>
              <div className="data-row">
                <span className="data-label">Throttle</span>
                <span className="data-value">L:{n.throttle_left || 0} R:{n.throttle_right || 0}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Battery & Hull */}
      <div className="card">
        <div className="card-header">Power & Hull</div>
        <div className="card-body">
          <div className="data-row">
            <span className="data-label">Battery</span>
            <span className={`data-value ${battClass(t.batt_v || 0)}`}>
              {(t.batt_v || 0).toFixed(1)}V ({t.batt_pct || 0}%)
            </span>
          </div>
          <div className="data-row">
            <span className="data-label">Hull</span>
            <span className={`data-value ${t.hull === 'DRY' ? 'ok' : 'danger'}`}>
              {t.hull || '---'}
            </span>
          </div>
          <div className="data-row">
            <span className="data-label">Motor temp</span>
            <span className={`data-value ${Math.max(t.mt_left || 0, t.mt_right || 0) > 70 ? 'warn' : ''}`}>
              L:{(t.mt_left || 0).toFixed(0)}° R:{(t.mt_right || 0).toFixed(0)}°
            </span>
          </div>
        </div>
      </div>

      {/* Environment */}
      <div className="card">
        <div className="card-header">Environment</div>
        <div className="card-body">
          <div className="data-row">
            <span className="data-label">Air</span>
            <span className="data-value">{e.air_temp || 0}°C {e.air_humidity || 0}%RH</span>
          </div>
          <div className="data-row">
            <span className="data-label">Water temp</span>
            <span className="data-value">
              {(e.water_temp || -999) === -999 ? '---' : `${e.water_temp.toFixed(1)}°C`}
            </span>
          </div>
          <div className="data-row">
            <span className="data-label">Salinity EC</span>
            <span className="data-value">{(e.water_ec || 0).toFixed(0)} µS/cm</span>
          </div>
          <div className="data-row">
            <span className="data-label">Light</span>
            <span className="data-value">{e.water_light || 0}%</span>
          </div>
          {e.bottom_contact && (
            <div className="data-row">
              <span className="data-label">Bottom</span>
              <span className="data-value warn">CONTACT</span>
            </div>
          )}
        </div>
      </div>

      {/* Sensor Health */}
      <div className="card">
        <div className="card-header">Sensor Health</div>
        <div className="card-body">
          <div className="health-grid">
            {HEALTH_LABELS.map((label, i) => {
              const flag = (t.health || '000000')[i]
              return (
                <div key={label} className={`health-item ${healthClass(flag)}`}>
                  {label}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}
