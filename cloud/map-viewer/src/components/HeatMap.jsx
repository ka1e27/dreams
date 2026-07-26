import { memo, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, useMap } from 'react-leaflet'

function sensorValue(reading, sensorType) {
  const v = reading[sensorType]
  return v !== null && v !== undefined ? v : 0
}

// Sequential blue -> cyan -> amber -> red scale. Deliberately avoids a green/red
// pairing (the classic red-green colorblindness confusion) and combines a hue
// shift with a luminance shift, so the ramp still reads correctly in grayscale
// or for colorblind viewers. Exported so App.jsx can render a legend gradient
// that is guaranteed to match what's actually drawn on the map.
export const HEAT_SCALE = [
  { stop: 0, color: [59, 130, 246] }, // blue-500
  { stop: 0.35, color: [34, 211, 238] }, // cyan-400
  { stop: 0.65, color: [251, 191, 36] }, // amber-400
  { stop: 1, color: [239, 68, 68] }, // red-500
]

export function valueToColor(value, min, max) {
  if (max === min) return '#38bdf8'
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)))
  for (let i = 0; i < HEAT_SCALE.length - 1; i++) {
    const a = HEAT_SCALE[i]
    const b = HEAT_SCALE[i + 1]
    if (ratio >= a.stop && ratio <= b.stop) {
      const t = (ratio - a.stop) / (b.stop - a.stop)
      const r = Math.round(a.color[0] + (b.color[0] - a.color[0]) * t)
      const g = Math.round(a.color[1] + (b.color[1] - a.color[1]) * t)
      const bl = Math.round(a.color[2] + (b.color[2] - a.color[2]) * t)
      return `rgb(${r}, ${g}, ${bl})`
    }
  }
  const last = HEAT_SCALE[HEAT_SCALE.length - 1].color
  return `rgb(${last[0]}, ${last[1]}, ${last[2]})`
}

function FitBounds({ readings }) {
  const map = useMap()
  useEffect(() => {
    if (readings.length === 0) return
    // Manual min/max loop instead of Math.min(...arr)/Math.max(...arr): spreading
    // a large array into call arguments risks "Maximum call stack size exceeded"
    // as point counts grow, and allocates two intermediate arrays for no benefit.
    let minLat = Infinity
    let maxLat = -Infinity
    let minLon = Infinity
    let maxLon = -Infinity
    for (const r of readings) {
      if (r.lat < minLat) minLat = r.lat
      if (r.lat > maxLat) maxLat = r.lat
      if (r.lon < minLon) minLon = r.lon
      if (r.lon > maxLon) maxLon = r.lon
    }
    map.fitBounds([
      [minLat - 0.001, minLon - 0.001],
      [maxLat + 0.001, maxLon + 0.001],
    ])
  }, [readings, map])
  return null
}

function HeatMap({ readings, track, sensorType, selectedMission }) {
  const filtered = useMemo(() => {
    let data = readings || []
    if (selectedMission) {
      data = data.filter(r => r.mission_name === selectedMission)
    }
    return data
  }, [readings, selectedMission])

  const { min, max } = useMemo(() => {
    if (filtered.length === 0) return { min: 0, max: 1 }
    let lo = Infinity
    let hi = -Infinity
    for (const r of filtered) {
      const v = sensorValue(r, sensorType)
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
    return { min: lo, max: hi }
  }, [filtered, sensorType])

  const trackPositions = useMemo(() =>
    (track || []).map(p => [p.lat, p.lon]),
    [track]
  )

  // Memoized so the (potentially thousands-long) marker list is only rebuilt
  // when the data that actually affects it changes — not on every render of
  // the parent (e.g. a `loading` flag flipping, or an unrelated track refresh).
  const markers = useMemo(() =>
    filtered.map((r, i) => {
      const v = sensorValue(r, sensorType)
      const color = valueToColor(v, min, max)
      return (
        <CircleMarker
          key={r.id ?? i}
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
    }),
    [filtered, sensorType, min, max]
  )

  return (
    <MapContainer
      center={[51.507, -0.071]}
      zoom={16}
      style={{ height: '100%', width: '100%' }}
      preferCanvas
    >
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
      {markers}
    </MapContainer>
  )
}

export default memo(HeatMap)
