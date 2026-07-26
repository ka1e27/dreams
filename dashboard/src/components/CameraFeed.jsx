import { useEffect, useRef, useState } from 'react'

function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const key = localStorage.getItem('boat_api_key') || ''
  const qs = key ? `?key=${encodeURIComponent(key)}` : ''
  return `${proto}://${window.location.host}${path}${qs}`
}

const WS_URL = wsUrl('/ws/camera')

export default function CameraFeed() {
  const imgRef = useRef(null)
  const [active, setActive] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws
    ws.binaryType = 'arraybuffer'
    let lastUrl = null

    ws.onopen = () => setActive(true)

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'image/jpeg' })
        const url = URL.createObjectURL(blob)
        if (imgRef.current) {
          imgRef.current.src = url
        }
        if (lastUrl) URL.revokeObjectURL(lastUrl)
        lastUrl = url
      }
    }

    ws.onclose = () => setActive(false)
    ws.onerror = () => ws.close()

    // Revoke the last outstanding blob: URL too — otherwise every
    // mount/unmount cycle (tab switch, HMR, etc.) leaked the final frame's
    // object URL, since only *previous* frames were revoked on swap.
    return () => {
      ws.close()
      if (lastUrl) URL.revokeObjectURL(lastUrl)
    }
  }, [])

  return (
    <div className="camera-panel">
      {active ? (
        <img ref={imgRef} alt="Camera" />
      ) : (
        <span className="camera-offline">Camera offline</span>
      )}
    </div>
  )
}
