import { useEffect, useRef, useState } from 'react'

const POLL_MS = 10000

function shallowEqual(a, b) {
  if (a === b) return true
  if (!a || !b) return false
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return false
  for (const k of ka) if (a[k] !== b[k]) return false
  return true
}

export function useNetwork(api) {
  const [network, setNetwork] = useState(null)
  const last = useRef(null)

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const s = await api.getNetworkStatus()
        if (cancelled) return
        if (!shallowEqual(s, last.current)) {
          last.current = s
          setNetwork(s)
        }
      } catch {
        if (cancelled) return
        if (last.current !== null) {
          last.current = null
          setNetwork(null)
        }
      }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [api])

  return network
}
