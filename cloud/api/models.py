"""SQLAlchemy models with PostGIS geometry columns."""
from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    """A georeferenced sensor reading from the boat's pod.

    Stores location as a PostGIS POINT(lon, lat) in SRID 4326 (WGS84).
    """
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    water_temp = Column(Float)
    salinity_ec = Column(Float)
    light_pct = Column(Integer)
    depth_m = Column(Float)
    air_temp = Column(Float)
    air_humidity = Column(Float)
    batt_v = Column(Float)
    mission_name = Column(String(100), index=True)
    waypoint_idx = Column(Integer)

    # Spatial index for bounding box queries
    __table_args__ = (
        Index("idx_readings_geom", geom, postgresql_using="gist"),
        Index("idx_readings_time_geom", "timestamp", geom, postgresql_using="gist"),
    )


class MissionTrack(Base):
    """GPS track point for mission playback."""
    __tablename__ = "mission_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    heading = Column(Float)
    speed_knots = Column(Float)
    mission_name = Column(String(100), index=True)

    __table_args__ = (
        Index("idx_track_geom", geom, postgresql_using="gist"),
        # Covers query_track's WHERE mission_name = ? AND timestamp BETWEEN ?
        # ORDER BY timestamp pattern with one index scan instead of two.
        Index("idx_track_mission_time", "mission_name", "timestamp"),
    )
