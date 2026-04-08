import { useCallback } from 'react'

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

  return {
    estop, resumeEstop, returnHome,
    pauseMission, resumeMission, abortMission, startMission,
    uploadMission, uploadAndStart, goto, getPodHistory,
  }
}
