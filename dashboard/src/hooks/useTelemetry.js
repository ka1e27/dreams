import { useState, useEffect, useRef, useCallback } from 'react'

function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const key = localStorage.getItem('boat_api_key') || ''
  const qs = key ? `?key=${encodeURIComponent(key)}` : ''
  return `${proto}://${window.location.host}${path}${qs}`
}

const WS_URL = wsUrl('/ws/telemetry')

export function useTelemetry() {
  const [data, setData] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      try {
        setData(JSON.parse(event.data))
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      reconnectTimer.current = setTimeout(connect, 2000)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { data, connected }
}
