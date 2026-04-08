"""Pydantic schemas for the cloud API."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class SensorReadingIn(BaseModel):
    """Ingest a single sensor reading."""
    timestamp: datetime.datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    water_temp: float | None = None
    salinity_ec: float | None = None
    light_pct: int | None = None
    depth_m: float | None = None
    air_temp: float | None = None
    air_humidity: float | None = None
    batt_v: float | None = None
    mission_name: str | None = None
    waypoint_idx: int | None = None


class SensorReadingOut(BaseModel):
    """A sensor reading in API responses."""
    id: int
    timestamp: datetime.datetime
    lat: float
    lon: float
    water_temp: float | None
    salinity_ec: float | None
    light_pct: int | None
    depth_m: float | None
    air_temp: float | None
    air_humidity: float | None
    batt_v: float | None
    mission_name: str | None
    waypoint_idx: int | None

    model_config = {"from_attributes": True}


class BatchIngestIn(BaseModel):
    """Batch ingest multiple readings."""
    readings: list[SensorReadingIn] = Field(min_length=1, max_length=500)


class BatchIngestOut(BaseModel):
    """Response for batch ingest."""
    ingested: int


class BboxQuery(BaseModel):
    """Bounding box + time range query parameters."""
    min_lat: float = Field(ge=-90, le=90)
    max_lat: float = Field(ge=-90, le=90)
    min_lon: float = Field(ge=-180, le=180)
    max_lon: float = Field(ge=-180, le=180)
    start: datetime.datetime | None = None
    end: datetime.datetime | None = None
    limit: int = Field(default=1000, ge=1, le=10000)


class TrackPointIn(BaseModel):
    """Ingest a GPS track point."""
    timestamp: datetime.datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    heading: float | None = None
    speed_knots: float | None = None
    mission_name: str | None = None


class TrackPointOut(BaseModel):
    """A track point in API responses."""
    id: int
    timestamp: datetime.datetime
    lat: float
    lon: float
    heading: float | None
    speed_knots: float | None
    mission_name: str | None

    model_config = {"from_attributes": True}
