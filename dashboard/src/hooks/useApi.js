import { useCallback, useMemo } from 'react'

const API_KEY = localStorage.getItem('boat_api_key') || ''

async function apiFetch(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (API_KEY) headers['X-API-Key'] = API_KEY

  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  return res.json()
}

export function useApi() {
  const estop = useCallback(() => apiFetch('/api/estop', { method: 'POST' }), [])
  const resumeEstop = useCallback(() => apiFetch('/api/resume', { method: 'POST' }), [])
  const returnHome = useCallback(() => apiFetch('/api/rth', { method: 'POST' }), [])
  const pauseMission = useCallback(() => apiFetch('/api/mission/pause', { method: 'POST' }), [])
  const resumeMission = useCallback(() => apiFetch('/api/mission/resume', { method: 'POST' }), [])
  const abortMission = useCallback(() => apiFetch('/api/mission/abort', { method: 'POST' }), [])
  const startMission = useCallback(() => apiFetch('/api/mission/start', { method: 'POST' }), [])

  const uploadMission = useCallback((mission) =>
    apiFetch('/api/mission?start=false', {
      method: 'POST',
      body: JSON.stringify(mission),
    }), [])

  const uploadAndStart = useCallback((mission) =>
    apiFetch('/api/mission?start=true', {
      method: 'POST',
      body: JSON.stringify(mission),
    }), [])

  const goto = useCallback((lat, lon) =>
    apiFetch('/api/goto', {
      method: 'POST',
      body: JSON.stringify({ lat, lon }),
    }), [])

  const getPodHistory = useCallback((limit = 100) =>
    apiFetch(`/api/pod/history?limit=${limit}`), [])

  const getNetworkStatus = useCallback(() => apiFetch('/api/network'), [])

  // Memoize the returned object so its identity is stable across renders.
  // Every method above is itself stable (useCallback, []), but the plain
  // object literal that wrapped them was recreated on every render, which
  // gave consumers (e.g. useNetwork's effect, keyed on `[api]`) a "new"
  // api reference on every App re-render — restarting that effect (and its
  // 10s poll interval) on every telemetry tick instead of once on mount.
  return useMemo(() => ({
    estop, resumeEstop, returnHome,
    pauseMission, resumeMission, abortMission, startMission,
    uploadMission, uploadAndStart, goto, getPodHistory,
    getNetworkStatus,
  }), [
    estop, resumeEstop, returnHome,
    pauseMission, resumeMission, abortMission, startMission,
    uploadMission, uploadAndStart, goto, getPodHistory,
    getNetworkStatus,
  ])
}
