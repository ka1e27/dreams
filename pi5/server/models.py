"""Pydantic models for API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TelemetryOut(BaseModel):
    """Live telemetry snapshot."""
    lat: float
    lon: float
    heading: float
    speed_knots: float
    batt_v: float
    batt_pct: int
    hull: str
    mt_left: float
    mt_right: float
    health: str


class EnvironmentOut(BaseModel):
    """Environment sensor snapshot."""
    air_temp: int
    air_humidity: int
    water_temp: float
    water_ec: float
    water_light: int
    bottom_contact: bool


class PodReadingOut(BaseModel):
    """A single pod sensor reading with timestamp."""
    timestamp: float
    water_temp: float
    salinity_ec: float
    light_pct: int
    bottom_contact: bool
    leak_detected: bool
    pressure_depth_m: float


class MissionWaypointIn(BaseModel):
    """A waypoint in a mission upload."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    type: str = Field(default="data", pattern="^(data|path)$")
    max_time: int = Field(default=300, ge=1, le=3600)
    label: str = ""


class MissionUploadIn(BaseModel):
    """Mission upload payload."""
    name: str = Field(min_length=1, max_length=100)
    waypoints: list[MissionWaypointIn] = Field(min_length=1)


class MissionStateOut(BaseModel):
    """Current mission execution state."""
    name: str
    running: bool
    paused: bool
    current_wp: int
    total_wps: int
    phase: str
    est_depth_m: float
    sample_count: int
    elapsed_s: float


class NavStateOut(BaseModel):
    """Current navigation state."""
    target_lat: float | None
    target_lon: float | None
    distance_m: float
    bearing_deg: float
    heading_error: float
    throttle_left: int
    throttle_right: int
    arrived: bool
    active: bool


class GotoIn(BaseModel):
    """GOTO command payload."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class StatusOut(BaseModel):
    """Full system status."""
    telemetry: TelemetryOut
    environment: EnvironmentOut
    navigation: NavStateOut
    mission: MissionStateOut
    connected: bool
