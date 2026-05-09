"""FastAPI application — REST API + WebSocket for the boat dashboard.

Endpoints:
  GET  /api/status          Full system status
  GET  /api/telemetry       Latest telemetry
  GET  /api/environment     Latest environment data
  GET  /api/pod/history     Pod reading history
  GET  /api/mission         Current mission state
  GET  /api/missions        List loaded missions
  POST /api/mission         Upload and optionally start a mission
  POST /api/mission/start   Start loaded mission
  POST /api/mission/pause   Pause mission
  POST /api/mission/resume  Resume mission
  POST /api/mission/abort   Abort mission
  POST /api/goto            Navigate to coordinates
  POST /api/estop           Emergency stop
  POST /api/resume          Resume after ESTOP
  POST /api/rth             Return to home
  WS   /ws/telemetry        Live telemetry stream
  WS   /ws/camera           Camera MJPEG stream
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import auth
from .models import (
    EnvironmentOut,
    GotoIn,
    MissionStateOut,
    MissionUploadIn,
    NavStateOut,
    PodReadingOut,
    StatusOut,
    TelemetryOut,
)
from .rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)

# These get injected by the main startup script
_pico = None      # PicoSerial
_navigator = None  # Navigator
_mission = None    # MissionManager
_pod = None        # PodBridge
_sim = None        # BoatSimulator (only in sim mode)
_camera = None     # cv.camera.CameraProducer (optional)
_network = None    # comms.network.NetworkManager (optional)
_winch_mode = "survey"
_home_lat = None
_home_lon = None


def configure(pico, navigator, mission_mgr, pod_bridge,
              home_lat=None, home_lon=None, api_key=None,
              cors_origins=None, simulator=None, camera=None,
              network=None, winch_mode="survey"):
    """Inject dependencies. Called before app startup."""
    global _pico, _navigator, _mission, _pod, _home_lat, _home_lon, _sim
    global _camera, _network, _winch_mode
    _pico = pico
    _navigator = navigator
    _mission = mission_mgr
    _pod = pod_bridge
    _home_lat = home_lat
    _home_lon = home_lon
    _sim = simulator
    _camera = camera
    _network = network
    _winch_mode = winch_mode
    auth.configure(api_key)

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


app = FastAPI(title="Autonomous Boat API", version="1.0.0")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def root():
    """Serve the dashboard UI."""
    return FileResponse(_STATIC_DIR / "index.html")

# Rate limiting — 60 req/min default, 10/min for sensitive endpoints
app.add_middleware(RateLimitMiddleware, default_rpm=60, burst_rpm=120)

# WebSocket connection managers
_tel_clients: list[WebSocket] = []
_cam_clients: list[WebSocket] = []


# ---- Helper to build response models from live state ----

def _tel_out() -> TelemetryOut:
    t = _pico.telemetry
    return TelemetryOut(
        lat=t.lat, lon=t.lon, heading=t.heading,
        speed_knots=t.speed_knots, batt_v=t.batt_v, batt_pct=t.batt_pct,
        hull=t.hull, mt_left=t.mt_left, mt_right=t.mt_right, health=t.health,
    )


def _env_out() -> EnvironmentOut:
    e = _pico.environment
    return EnvironmentOut(
        air_temp=e.air_temp, air_humidity=e.air_humidity,
        water_temp=e.water_temp, water_ec=e.water_ec,
        water_light=e.water_light, bottom_contact=e.bottom_contact,
    )


def _nav_out() -> NavStateOut:
    n = _navigator.state
    return NavStateOut(
        target_lat=n.target_lat, target_lon=n.target_lon,
        distance_m=n.distance_m, bearing_deg=n.bearing_deg,
        heading_error=n.heading_error,
        throttle_left=n.throttle_left, throttle_right=n.throttle_right,
        arrived=n.arrived, active=n.active,
    )


def _mission_out() -> MissionStateOut:
    m = _mission.state
    return MissionStateOut(
        name=m.name, running=m.running, paused=m.paused,
        current_wp=m.current_wp, total_wps=m.total_wps,
        phase=m.phase.name, est_depth_m=m.est_depth_m,
        sample_count=m.sample_count, elapsed_s=m.elapsed_s,
    )


# ---- REST Endpoints ----

@app.get("/api/status", response_model=StatusOut)
async def get_status(_: str = Depends(auth.require_api_key)):
    """Full system status snapshot."""
    return StatusOut(
        telemetry=_tel_out(),
        environment=_env_out(),
        navigation=_nav_out(),
        mission=_mission_out(),
        connected=_pico.connected,
    )


@app.get("/api/telemetry", response_model=TelemetryOut)
async def get_telemetry(_: str = Depends(auth.require_api_key)):
    """Latest telemetry."""
    return _tel_out()


@app.get("/api/network")
async def get_network_status(_: str = Depends(auth.require_api_key)):
    """Active network transport (wifi / cellular / offline) and online state."""
    if _network is None:
        return {"mode": "unknown", "active_kind": "unknown",
                "active_interface": None, "online": False}
    return _network.status()


@app.get("/api/environment", response_model=EnvironmentOut)
async def get_environment(_: str = Depends(auth.require_api_key)):
    """Latest environment sensor data."""
    return _env_out()


@app.get("/api/pod/history", response_model=list[PodReadingOut])
async def get_pod_history(
    limit: int = 100,
    _: str = Depends(auth.require_api_key),
):
    """Pod reading history (most recent first)."""
    readings = _pod.history[-limit:]
    readings.reverse()
    return [
        PodReadingOut(
            timestamp=r.timestamp, water_temp=r.water_temp,
            salinity_ec=r.salinity_ec, light_pct=r.light_pct,
            bottom_contact=r.bottom_contact, leak_detected=r.leak_detected,
            pressure_depth_m=r.pressure_depth_m,
        )
        for r in readings
    ]


@app.get("/api/mission", response_model=MissionStateOut)
async def get_mission(_: str = Depends(auth.require_api_key)):
    """Current mission state."""
    return _mission_out()


@app.post("/api/mission", response_model=MissionStateOut)
async def upload_mission(
    payload: MissionUploadIn,
    start: bool = False,
    _: str = Depends(auth.require_api_key),
):
    """Upload a mission. Optionally start it immediately with ?start=true."""
    data = {
        "name": payload.name,
        "waypoints": [wp.model_dump() for wp in payload.waypoints],
    }
    if not _mission.load_from_dict(data):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid mission data")
    if start:
        await _mission.start()
    return _mission_out()


@app.post("/api/mission/start")
async def start_mission(_: str = Depends(auth.require_api_key)):
    """Start the loaded mission."""
    if not _mission.waypoints:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No mission loaded")
    await _mission.start()
    return {"status": "started"}


@app.post("/api/mission/pause")
async def pause_mission(_: str = Depends(auth.require_api_key)):
    """Pause the running mission."""
    _mission.pause()
    return {"status": "paused"}


@app.post("/api/mission/resume")
async def resume_mission(_: str = Depends(auth.require_api_key)):
    """Resume the paused mission."""
    _mission.resume_mission()
    return {"status": "resumed"}


@app.post("/api/mission/abort")
async def abort_mission(_: str = Depends(auth.require_api_key)):
    """Abort the running mission."""
    _mission.abort("API_ABORT")
    return {"status": "aborted"}


@app.post("/api/mission/skip")
async def skip_site(_: str = Depends(auth.require_api_key)):
    """Skip the current data waypoint — winch up and continue mission."""
    _mission.skip_site()
    return {"status": "skipping"}


@app.post("/api/goto")
async def goto(
    payload: GotoIn,
    _: str = Depends(auth.require_api_key),
):
    """Navigate to a specific coordinate."""
    if _mission.state.running:
        _mission.abort("GOTO_OVERRIDE")
    _navigator.goto(payload.lat, payload.lon)
    return {"status": "navigating", "lat": payload.lat, "lon": payload.lon}


@app.post("/api/estop")
async def estop(_: str = Depends(auth.require_api_key)):
    """Emergency stop — kill all motors."""
    if _mission.state.running:
        _mission.abort("ESTOP")
    _navigator.stop_nav()
    await _pico.emergency_stop()
    return {"status": "emergency_stop"}


@app.post("/api/resume")
async def resume_estop(_: str = Depends(auth.require_api_key)):
    """Resume after emergency stop."""
    await _pico.resume()
    return {"status": "resumed"}


@app.get("/api/mission/waypoints")
async def get_mission_waypoints(_: str = Depends(auth.require_api_key)):
    """Return the loaded mission waypoints."""
    return [
        {"lat": wp.lat, "lon": wp.lon, "type": wp.wp_type.name.lower(), "label": wp.label}
        for wp in _mission.waypoints
    ]


@app.post("/api/sim/speed")
async def set_sim_speed(
    payload: dict,
    _: str = Depends(auth.require_api_key),
):
    """Set simulator speed (max_speed_mps). Only works in simulator mode."""
    if _sim is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Not in simulator mode")
    speed = payload.get("max_speed_mps")
    if speed is None or not (0.1 <= speed <= 50.0):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="max_speed_mps must be 0.1–50.0")
    _sim._config.max_speed_mps = float(speed)
    return {"status": "ok", "max_speed_mps": _sim._config.max_speed_mps}


@app.get("/api/sim/speed")
async def get_sim_speed(_: str = Depends(auth.require_api_key)):
    """Get current simulator speed."""
    if _sim is None:
        return {"max_speed_mps": None}
    return {"max_speed_mps": _sim._config.max_speed_mps}


@app.post("/api/nav/throttle")
async def set_cruise_throttle(
    payload: dict,
    _: str = Depends(auth.require_api_key),
):
    """Set cruise throttle (0–100)."""
    val = payload.get("cruise_throttle")
    if val is None or not (1 <= val <= 100):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="cruise_throttle must be 1–100")
    _navigator._config.cruise_throttle = int(val)
    return {"status": "ok", "cruise_throttle": _navigator._config.cruise_throttle}


@app.get("/api/nav/throttle")
async def get_cruise_throttle(_: str = Depends(auth.require_api_key)):
    """Get current cruise throttle."""
    return {"cruise_throttle": _navigator._config.cruise_throttle}


@app.post("/api/winch/speed")
async def set_winch_speed(
    payload: dict,
    _: str = Depends(auth.require_api_key),
):
    """Set winch down/up speeds."""
    down = payload.get("down_speed")
    up = payload.get("up_speed")
    cfg = _mission._config
    if down is not None:
        if not (1 <= down <= 100):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="down_speed must be 1–100")
        cfg.winch_down_speed = int(down)
    if up is not None:
        if not (-100 <= up <= -1):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="up_speed must be -100 to -1")
        cfg.winch_up_speed = int(up)
    return {"status": "ok", "down_speed": cfg.winch_down_speed, "up_speed": cfg.winch_up_speed}


@app.get("/api/winch/speed")
async def get_winch_speed(_: str = Depends(auth.require_api_key)):
    """Get current winch speeds."""
    cfg = _mission._config
    return {"down_speed": cfg.winch_down_speed, "up_speed": cfg.winch_up_speed}


@app.post("/api/rth")
async def return_to_home(_: str = Depends(auth.require_api_key)):
    """Return to home position."""
    if _home_lat is None or _home_lon is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No home position configured")
    await _mission.return_to_home(_home_lat, _home_lon)
    return {"status": "returning_home", "lat": _home_lat, "lon": _home_lon}


# ---- WebSocket: Live Telemetry ----

@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    """Stream live telemetry as JSON at ~1Hz.

    Authenticate via query param: /ws/telemetry?key=<api_key>
    """
    if not await auth.validate_ws(ws):
        return
    await ws.accept()
    _tel_clients.append(ws)
    try:
        while True:
            data = {
                "telemetry": _tel_out().model_dump(),
                "environment": _env_out().model_dump(),
                "navigation": _nav_out().model_dump(),
                "mission": _mission_out().model_dump(),
                "timestamp": time.time(),
            }
            await ws.send_json(data)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS telemetry error: %s", e)
    finally:
        if ws in _tel_clients:
            _tel_clients.remove(ws)


# ---- WebSocket: Camera Stream ----

@app.websocket("/ws/camera")
async def ws_camera(ws: WebSocket):
    """Stream MJPEG frames from the shared camera producer.

    Authenticate via query param: /ws/camera?key=<api_key>
    Optional ?cam=left|right|disparity selects the view. Defaults to left.
    The producer is owned by the app lifespan; this handler just subscribes.
    """
    if not await auth.validate_ws(ws):
        return
    await ws.accept()
    _cam_clients.append(ws)

    try:
        import cv2
        import numpy as np
    except ImportError:
        await ws.send_json({"error": "opencv not installed"})
        await ws.close()
        if ws in _cam_clients:
            _cam_clients.remove(ws)
        return

    if _camera is None:
        await ws.send_json({"error": "camera producer not running"})
        await ws.close()
        if ws in _cam_clients:
            _cam_clients.remove(ws)
        return

    view = ws.query_params.get("cam", "left")
    queue = _camera.subscribe()

    # Disparity view uses StereoSGBM if calibration is loaded; lazy import.
    stereo = None
    if view == "disparity":
        try:
            from ..cv.stereo import StereoDepth, load_calibration
            calib = load_calibration("pi5/cv/calibration.npz")
            if calib is not None:
                stereo = StereoDepth(calib)
        except Exception as e:
            logger.warning("disparity view fell back to left: %s", e)
            view = "left"

    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            if view == "right" and frame.right is not None:
                img = frame.right
            elif view == "disparity" and stereo is not None and frame.right is not None:
                disp, _ = stereo.compute(frame.left, frame.right)
                disp_norm = cv2.normalize(disp, None, 0, 255,
                                          cv2.NORM_MINMAX).astype(np.uint8)
                img = cv2.applyColorMap(disp_norm, cv2.COLORMAP_TURBO)
            else:
                img = frame.left
            _, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
            await ws.send_bytes(jpeg.tobytes())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS camera error: %s", e)
    finally:
        _camera.unsubscribe(queue)
        if ws in _cam_clients:
            _cam_clients.remove(ws)
