import { useEffect, useRef, useState } from 'react'

// Confirmed, geolocated objects (buoys / landmarks / people) the boat's vision
// memory has charted — polled for the map layer. Kept slow (a couple of seconds)
// because the set changes only when a new object is confirmed or one expires.
const POLL_MS = 2500

export function useMapObjects(api) {
  const [objects, setObjects] = useState([])
  const lastKey = useRef('')

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const r = await api.getMapObjects()
        if (cancelled) return
        const objs = (r && r.available && Array.isArray(r.objects)) ? r.objects : []
        // Only re-render when something actually changed (id/position/sightings).
        const key = objs.map(o => `${o.id}:${o.lat},${o.lon}:${o.sightings}`).join('|')
        if (key !== lastKey.current) {
          lastKey.current = key
          setObjects(objs)
        }
      } catch {
        if (cancelled) return
        if (lastKey.current !== '') {
          lastKey.current = ''
          setObjects([])
        }
      }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [api])

  return objects
}
