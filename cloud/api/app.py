"""Cloud API — ingest and query georeferenced sensor data.

Endpoints:
  POST /api/v1/readings         Ingest a batch of sensor readings
  GET  /api/v1/readings         Query readings by bounding box + time range
  POST /api/v1/track            Ingest GPS track points
  GET  /api/v1/track            Query track by mission name + time range
  GET  /api/v1/missions         List distinct mission names
  GET  /health                  Health check
"""
from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager

from database import get_db, init_db
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from geoalchemy2.functions import ST_MakeEnvelope, ST_MakePoint, ST_Within
from models import MissionTrack, SensorReading
from schemas import (
    BatchIngestIn,
    BatchIngestOut,
    SensorReadingOut,
    TrackPointIn,
    TrackPointOut,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key = os.environ.get("CLOUD_API_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database tables created/verified")
    yield


app = FastAPI(title="Boat Cloud API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Map viewer can run anywhere
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def require_api_key(key: str | None = Security(_api_key_header)) -> str:
    """Validate API key. Skips if not configured."""
    if not _api_key:
        return "dev-mode"
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not hmac.compare_digest(key.encode(), _api_key.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


# ---- Health ----

@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check — verifies database connectivity."""
    try:
        db.execute(select(func.now()))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database error: %s" % e)


# ---- Sensor Readings ----

@app.post("/api/v1/readings", response_model=BatchIngestOut)
async def ingest_readings(
    payload: BatchIngestIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Ingest a batch of sensor readings with GPS coordinates."""
    objects = []
    for r in payload.readings:
        reading = SensorReading(
            timestamp=r.timestamp,
            lat=r.lat,
            lon=r.lon,
            geom=ST_MakePoint(r.lon, r.lat, type_=None),
            water_temp=r.water_temp,
            salinity_ec=r.salinity_ec,
            light_pct=r.light_pct,
            depth_m=r.depth_m,
            air_temp=r.air_temp,
            air_humidity=r.air_humidity,
            batt_v=r.batt_v,
            mission_name=r.mission_name,
            waypoint_idx=r.waypoint_idx,
        )
        objects.append(reading)
    db.add_all(objects)
    db.commit()
    return BatchIngestOut(ingested=len(objects))


@app.get("/api/v1/readings", response_model=list[SensorReadingOut])
async def query_readings(
    min_lat: float = Query(ge=-90, le=90),
    max_lat: float = Query(ge=-90, le=90),
    min_lon: float = Query(ge=-180, le=180),
    max_lon: float = Query(ge=-180, le=180),
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Query sensor readings within a bounding box and optional time range.

    The bounding box uses PostGIS ST_MakeEnvelope for efficient spatial queries
    against the GiST index on the geom column.
    """
    bbox = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    query = (
        select(SensorReading)
        .where(ST_Within(SensorReading.geom, bbox))
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
    )
    if start:
        query = query.where(SensorReading.timestamp >= start)
    if end:
        query = query.where(SensorReading.timestamp <= end)

    results = db.execute(query).scalars().all()
    return results


# ---- Track Points ----

@app.post("/api/v1/track", response_model=BatchIngestOut)
async def ingest_track(
    points: list[TrackPointIn],
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Ingest GPS track points for mission playback."""
    objects = []
    for p in points:
        track = MissionTrack(
            timestamp=p.timestamp,
            lat=p.lat,
            lon=p.lon,
            geom=ST_MakePoint(p.lon, p.lat, type_=None),
            heading=p.heading,
            speed_knots=p.speed_knots,
            mission_name=p.mission_name,
        )
        objects.append(track)
    db.add_all(objects)
    db.commit()
    return BatchIngestOut(ingested=len(objects))


@app.get("/api/v1/track", response_model=list[TrackPointOut])
async def query_track(
    mission_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Query GPS track points, optionally filtered by mission name and time."""
    query = (
        select(MissionTrack)
        .order_by(MissionTrack.timestamp.asc())
        .limit(limit)
    )
    if mission_name:
        query = query.where(MissionTrack.mission_name == mission_name)
    if start:
        query = query.where(MissionTrack.timestamp >= start)
    if end:
        query = query.where(MissionTrack.timestamp <= end)

    results = db.execute(query).scalars().all()
    return results


# ---- Missions ----

@app.get("/api/v1/missions")
async def list_missions(
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """List distinct mission names with reading counts."""
    query = (
        select(
            SensorReading.mission_name,
            func.count(SensorReading.id).label("reading_count"),
            func.min(SensorReading.timestamp).label("first_reading"),
            func.max(SensorReading.timestamp).label("last_reading"),
        )
        .where(SensorReading.mission_name.isnot(None))
        .group_by(SensorReading.mission_name)
        .order_by(func.max(SensorReading.timestamp).desc())
    )
    results = db.execute(query).all()
    return [
        {
            "mission_name": r.mission_name,
            "reading_count": r.reading_count,
            "first_reading": r.first_reading.isoformat() if r.first_reading else None,
            "last_reading": r.last_reading.isoformat() if r.last_reading else None,
        }
        for r in results
    ]
