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

    ws.onopen = () => setActive(true)

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'image/jpeg' })
        const url = URL.createObjectURL(blob)
        if (imgRef.current) {
          const prev = imgRef.current.src
          imgRef.current.src = url
          if (prev.startsWith('blob:')) URL.revokeObjectURL(prev)
        }
      }
    }

    ws.onclose = () => setActive(false)
    ws.onerror = () => ws.close()

    return () => ws.close()
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
