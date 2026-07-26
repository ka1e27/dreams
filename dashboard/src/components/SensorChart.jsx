import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const MAX_POINTS = 120  // ~2 minutes of history at 1Hz

export default function SensorChart({ telemetry, environment }) {
  const [history, setHistory] = useState([])

  useEffect(() => {
    if (!telemetry) return
    const now = new Date()
    const point = {
      time: `${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`,
      batt: telemetry.batt_v || 0,
      water_t: environment?.water_temp !== -999 ? environment?.water_temp || null : null,
      ec: environment?.water_ec || 0,
      speed: telemetry.speed_knots || 0,
    }
    setHistory(prev => [...prev.slice(-MAX_POINTS), point])
  }, [telemetry, environment])

  if (history.length < 2) {
    return (
      <div className="chart-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>Collecting data...</span>
      </div>
    )
  }

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={history} margin={{ top: 4, right: 12, bottom: 4, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2d3d" />
          <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#7d8aa0' }} interval="preserveStartEnd" />
          <YAxis yAxisId="left" tick={{ fontSize: 9, fill: '#7d8aa0' }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 9, fill: '#7d8aa0' }} />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #1e2d3d', fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <Line yAxisId="left" type="monotone" dataKey="batt" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Battery (V)" />
          <Line yAxisId="left" type="monotone" dataKey="water_t" stroke="#38bdf8" strokeWidth={1.5} dot={false} name="Water °C" connectNulls />
          <Line yAxisId="right" type="monotone" dataKey="ec" stroke="#22c55e" strokeWidth={1} dot={false} name="EC µS/cm" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
