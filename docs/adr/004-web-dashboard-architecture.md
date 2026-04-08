# ADR-004: Web Dashboard and API Architecture

**Date**: 2026-04-08  
**Status**: proposed  
**Deciders**: Kyle (project owner), Claude (architect)

## Context

The boat needs a web-based dashboard accessible from a phone at the waterside over cellular. It must show real-time telemetry, support mission planning (click-to-place waypoints), and provide control buttons (ESTOP, RTH, pause/resume).

## Decisions

### 1. FastAPI for the server

**Why:** Async-native (same event loop as navigation), built-in WebSocket support, automatic OpenAPI docs, Pydantic validation. Lightweight enough for Pi 5.

### 2. WebSocket for live telemetry, REST for commands

- `/ws/telemetry` streams JSON at 1Hz — telemetry, environment, navigation, mission state all in one frame
- `/ws/camera` streams binary JPEG frames (~10fps)
- REST POST endpoints for commands (estop, goto, mission upload) — these are one-shot operations that benefit from proper HTTP status codes

**Why:** WebSocket avoids polling overhead for high-frequency data. REST gives proper semantics for commands (201 on create, 400 on bad input, 401/403 on auth failure).

### 3. API key authentication via X-API-Key header

All endpoints require a valid `X-API-Key` header. The key is set via `BOAT_API_KEY` environment variable. In dev mode (no key set), all endpoints are open.

**Why this is not enough for production:** The server will be exposed over cellular internet. Before deploying:
- Use HTTPS (Let's Encrypt or reverse proxy)
- Rate-limit all endpoints
- Consider adding TOTP or per-session tokens
- The current API key is a shared secret — adequate for a single operator, not for multi-user

### 4. React + Vite dashboard with dark maritime theme

**Design choices:**
- CARTO dark basemap tiles (works well at sea — low contrast, no distracting colours)
- Dark theme (`#0a0f1a` background) — reduces glare at waterside
- Monospace font throughout — numerical data reads better
- Responsive grid layout — collapses to single column on mobile
- Leaflet for maps (lighter than Mapbox, works offline with cached tiles)
- Recharts for sensor time-series (lightweight, React-native)

### 5. Click-to-place waypoint planning

Users click on the map to place waypoints (defaulting to DATA type). A "Start Mission" button uploads the waypoint list to the Pi 5 and begins execution. This replaces the old workflow of manually typing coordinates into the Shore Pico terminal.

### 6. Camera stream via WebSocket binary frames

Binary JPEG frames over WebSocket rather than MJPEG over HTTP because:
- WebSocket is already open for telemetry
- Binary frames have less overhead than HTTP multipart boundaries
- Client-side rendering is simple: create blob URL, set img.src
- OpenCV is already needed for future obstacle detection, so cv2.imencode is free

## Security Review

| Area | Status | Notes |
|------|--------|-------|
| Authentication | Done | API key via X-API-Key header, constant-time comparison (hmac.compare_digest) |
| WebSocket auth | Done | Validates `?key=` query param or X-API-Key header on connect. Closes with 4003 on failure. |
| Rate limiting | Done | In-memory sliding window. 60 req/min default, 10/min for ESTOP/RTH/mission. Per-IP. |
| Input validation | Done | Pydantic models validate all POST bodies. Lat/lon bounds checked. |
| CORS | Done | Restricted to configured origins only. |
| HTTPS | Done | Caddy reverse proxy with auto-TLS via Let's Encrypt. HSTS header. See `deploy/Caddyfile`. |
| SQL injection | N/A | No database in this component. |
| Command injection | N/A | No shell exec. All commands go through typed Python API. |
| Request size | Done | Caddy limits request body to 1MB. |

**Before field deployment:**
1. Set `BOAT_API_KEY` to a strong random value: `export BOAT_API_KEY=$(openssl rand -hex 32)`
2. Set up DNS and Caddy per `deploy/setup-https.md`

## Consequences

### Positive
- Single-page app works on phone browsers — no native app needed
- Real-time updates with sub-second latency
- Mission planning is visual and intuitive
- Camera feed enables remote monitoring

### Negative
- Depends on cellular connectivity for shore access
- OpenCV is a heavy dependency just for JPEG encoding (future CV work justifies it)
- No offline capability in the dashboard (could add service worker later)
