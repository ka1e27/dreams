import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, useMap } from 'react-leaflet'

function sensorValue(reading, sensorType) {
  const v = reading[sensorType]
  return v !== null && v !== undefined ? v : 0
}

function valueToColor(value, min, max) {
  if (max === min) return '#38bdf8'
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)))
  // Green → Yellow → Red
  if (ratio < 0.5) {
    const r = Math.round(255 * (ratio * 2))
    return `rgb(${r}, 200, 80)`
  } else {
    const g = Math.round(200 * (1 - (ratio - 0.5) * 2))
    return `rgb(240, ${g}, 60)`
  }
}

function FitBounds({ readings }) {
  const map = useMap()
  useEffect(() => {
    if (readings.length === 0) return
    const lats = readings.map(r => r.lat)
    const lons = readings.map(r => r.lon)
    map.fitBounds([
      [Math.min(...lats) - 0.001, Math.min(...lons) - 0.001],
      [Math.max(...lats) + 0.001, Math.max(...lons) + 0.001],
    ])
  }, [readings, map])
  return null
}

export default function HeatMap({ readings, track, sensorType, selectedMission }) {
  const filtered = useMemo(() => {
    let data = readings || []
    if (selectedMission) {
      data = data.filter(r => r.mission_name === selectedMission)
    }
    return data
  }, [readings, selectedMission])

  const { min, max } = useMemo(() => {
    if (filtered.length === 0) return { min: 0, max: 1 }
    const values = filtered.map(r => sensorValue(r, sensorType)).filter(v => v !== null)
    return {
      min: Math.min(...values),
      max: Math.max(...values),
    }
  }, [filtered, sensorType])

  const trackPositions = useMemo(() =>
    (track || []).map(p => [p.lat, p.lon]),
    [track]
  )

  return (
    <MapContainer center={[51.507, -0.071]} zoom={16} style={{ height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; CARTO'
      />
      <FitBounds readings={filtered} />

      {/* Track line */}
      {trackPositions.length > 1 && (
        <Polyline positions={trackPositions} color="#38bdf8" weight={2} opacity={0.4} />
      )}

      {/* Data points as coloured circles */}
      {filtered.map((r, i) => {
        const v = sensorValue(r, sensorType)
        const color = valueToColor(v, min, max)
        return (
          <CircleMarker
            key={r.id || i}
            center={[r.lat, r.lon]}
            radius={6}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.8, weight: 1 }}
          >
            <Tooltip>
              <div style={{ fontFamily: 'monospace', fontSize: 11 }}>
                <strong>{sensorType}: {v !== null ? v.toFixed(1) : '—'}</strong><br />
                T: {r.water_temp?.toFixed(1) ?? '—'}°C &nbsp;
                EC: {r.salinity_ec?.toFixed(0) ?? '—'} µS/cm<br />
                Depth: {r.depth_m?.toFixed(1) ?? '—'}m &nbsp;
                Light: {r.light_pct ?? '—'}%<br />
                {r.mission_name && <>Mission: {r.mission_name}<br /></>}
                {new Date(r.timestamp).toLocaleString()}
              </div>
            </Tooltip>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
