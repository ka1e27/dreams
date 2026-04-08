# ADR-005: Cloud Data Pipeline

**Date**: 2026-04-08  
**Status**: proposed  
**Deciders**: Kyle (project owner), Claude (architect)

## Context

Sensor readings need to be stored centrally for post-mission analysis, heatmap visualization, and long-term data collection. The Pi 5 has unreliable cellular connectivity, so data must buffer locally and upload when online.

## Decisions

### 1. PostgreSQL + PostGIS for spatial queries

Sensor readings are georeferenced (lat/lon). PostGIS enables efficient bounding-box queries via GiST-indexed geometry columns, which is exactly what the heatmap viewer needs.

### 2. Batch ingest endpoint (up to 500 readings per request)

The Pi 5 uploader collects readings over time and sends them in batches. This is more efficient than individual inserts and tolerates intermittent connectivity — one successful POST can upload minutes of data.

### 3. Local JSON buffer on the Pi 5

When cellular is down, readings accumulate in `upload_buffer.json`. On startup, the uploader loads any buffered data from the previous session. This survives Pi 5 reboots and ensures no data loss during connectivity gaps.

### 4. Docker Compose for local development

`docker-compose.yml` spins up PostGIS + the API for local testing. The same API image can be deployed to any cloud provider.

### 5. Separate map viewer from the boat dashboard

The map viewer is a different audience (post-mission analysis) with different requirements (historical data, heatmaps, filtering). Keeping it separate avoids bloating the real-time dashboard.

### Security Review

| Area | Status |
|------|--------|
| API key auth | Done — constant-time comparison |
| Input validation | Done — Pydantic with lat/lon bounds |
| SQL injection | Safe — SQLAlchemy parameterized queries throughout |
| Batch size limits | Done — max 500 readings per request |
| CORS | Permissive (`*`) since the viewer may run from any origin |

## Consequences

### Positive
- Spatial queries via PostGIS are fast even with millions of readings
- Local buffering means zero data loss during cellular outages
- Docker Compose makes local development trivial
- Map viewer works independently of the boat

### Negative
- Requires a PostgreSQL + PostGIS server to be hosted somewhere
- GeoAlchemy2 adds a dependency chain (requires libgeos)
