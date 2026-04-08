import { useEffect, useRef, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Circle, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'

const BOAT_ICON = L.divIcon({
  className: '',
  html: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
    <path d="M12 2L6 18h12L12 2z" fill="#38bdf8" stroke="#0c4a6e" stroke-width="1.5"/>
  </svg>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

const WP_DATA_ICON = L.divIcon({
  className: '',
  html: `<div style="width:12px;height:12px;border-radius:50%;background:#38bdf8;border:2px solid #0c4a6e;"></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6],
})

const WP_PATH_ICON = L.divIcon({
  className: '',
  html: `<div style="width:8px;height:8px;border-radius:50%;background:#64748b;border:2px solid #334155;"></div>`,
  iconSize: [8, 8],
  iconAnchor: [4, 4],
})

function BoatMarker({ lat, lon, heading }) {
  const markerRef = useRef(null)

  useEffect(() => {
    if (markerRef.current) {
      const el = markerRef.current.getElement()
      if (el) {
        el.style.transform += ` rotate(${heading}deg)`
        el.style.transformOrigin = 'center center'
      }
    }
  }, [heading])

  if (!lat || !lon) return null
  return <Marker ref={markerRef} position={[lat, lon]} icon={BOAT_ICON} />
}

function MapFollower({ lat, lon }) {
  const map = useMap()
  useEffect(() => {
    if (lat && lon) map.setView([lat, lon], map.getZoom(), { animate: true })
  }, [lat, lon, map])
  return null
}

function MapClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      if (onMapClick) onMapClick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

export default function BoatMap({ telemetry, mission, waypoints, onMapClick, track }) {
  const lat = telemetry?.lat || 51.506726
  const lon = telemetry?.lon || -0.071438
  const heading = telemetry?.heading || 0

  const wpPositions = useMemo(() =>
    (waypoints || []).map(wp => [wp.lat, wp.lon]),
    [waypoints]
  )

  const trackPositions = useMemo(() =>
    (track || []).map(p => [p[0], p[1]]),
    [track]
  )

  return (
    <MapContainer center={[lat, lon]} zoom={17} style={{ height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com">CARTO</a>'
      />
      <MapFollower lat={lat} lon={lon} />
      <MapClickHandler onMapClick={onMapClick} />
      <BoatMarker lat={lat} lon={lon} heading={heading} />

      {/* Waypoint markers */}
      {(waypoints || []).map((wp, i) => (
        <Marker
          key={i}
          position={[wp.lat, wp.lon]}
          icon={wp.type === 'data' ? WP_DATA_ICON : WP_PATH_ICON}
        />
      ))}

      {/* Mission route line */}
      {wpPositions.length > 1 && (
        <Polyline positions={wpPositions} color="#38bdf8" weight={1.5} opacity={0.5} dashArray="8 4" />
      )}

      {/* Arrival radius circle */}
      {waypoints?.length > 0 && mission?.running && mission.current_wp < waypoints.length && (
        <Circle
          center={[waypoints[mission.current_wp].lat, waypoints[mission.current_wp].lon]}
          radius={5}
          pathOptions={{ color: '#38bdf8', fillOpacity: 0.1, weight: 1 }}
        />
      )}

      {/* Track line */}
      {trackPositions.length > 1 && (
        <Polyline positions={trackPositions} color="#22c55e" weight={2} opacity={0.6} />
      )}
    </MapContainer>
  )
}
