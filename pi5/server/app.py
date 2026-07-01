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
import base64
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

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
_overlay = None    # cv.vision_overlay.DetectionOverlay (optional)
_network = None    # comms.network.NetworkManager (optional)
_stepper = None    # cv.stepper.StepperMotor (optional, radar-bar pan)
_radar = None      # cv.radar_tracker.RadarTracker (optional)
_winch_mode = "survey"
_home_lat = None
_home_lon = None


def configure(pico, navigator, mission_mgr, pod_bridge,
              home_lat=None, home_lon=None, api_key=None,
              cors_origins=None, simulator=None, camera=None,
              network=None, winch_mode="survey", overlay=None,
              jpeg_quality=60, stream_fps=15, stepper=None, radar=None):
    """Inject dependencies. Called before app startup."""
    global _pico, _navigator, _mission, _pod, _home_lat, _home_lon, _sim
    global _camera, _network, _winch_mode, _overlay, _jpeg_quality, _stream_fps_cap
    global _stepper, _radar
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
    _overlay = overlay
    _jpeg_quality = int(jpeg_quality)
    _stream_fps_cap = float(stream_fps)
    _stepper = stepper
    _radar = radar
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

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.get("/", include_in_schema=False)
async def root():
    """Serve the command center — the single UI (map, telemetry, camera, health, controls)."""
    return FileResponse(_TEMPLATES_DIR / "command_center.html")


@app.get("/command", include_in_schema=False)
async def command_center():
    """Legacy path — the command center is now served at /."""
    return RedirectResponse(url="/")

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


# ============================================================================
# Command Center — camera MJPEG, Pi 5 health, and Pico terminal
# ----------------------------------------------------------------------------
# These endpoints power /command (templates/command_center.html). They extend
# the existing app without disturbing the navigation API above:
#   * /video reuses the shared CameraProducer (_camera) — it never opens a
#     second VideoCapture, so it can't contend with the CV pipeline.
#   * /ws/pico streams *parsed* frames from the existing PicoSerial (_pico) and
#     can dispatch protocol commands — it does not open a second serial reader.
#   * /pico/push reflashes the Pico via mpremote, releasing and re-acquiring the
#     port around the operation. Hardware-only; refuses while a mission runs.
# Everything degrades cleanly in simulator mode and on non-Pi hosts.
# ============================================================================

# 640x360 near-black JPEG shown when no camera producer is running.
_NO_CAM_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIf"
    "IiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAFoAoADASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDySiii"
    "gAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKK"
    "KACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAoo"
    "ooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA"
    "KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAo"
    "oooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACii"
    "igAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAC"
    "iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK"
    "ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK"
    "KKACiiigAooooAKKKKACiiigAooooA//9k="
)

_latest_health: dict | None = None
_health_task: asyncio.Task[None] | None = None
_cam_fps: float = 0.0  # rolling estimate updated by the /video streamer
_net_prev: tuple[int, int, float] | None = None  # (bytes_sent, bytes_recv, monotonic)
_jpeg_quality: int = 60      # /video MJPEG quality (runtime-adjustable via /api/camera)
_stream_fps_cap: float = 15.0  # /video publish-rate cap (runtime-adjustable)


def _http_key_ok(request: Request) -> bool:
    """Validate an API key passed via ?key= or X-API-Key for plain-HTTP routes.

    Used by /video, whose <img> tag can't attach an auth header. Mirrors the
    dev-mode behaviour of auth.require_api_key (open when no key configured).
    """
    key = request.query_params.get("key") or request.headers.get("x-api-key")
    return auth.key_valid(key)


# ---- Pi 5 health ----

async def _vcgencmd(*args: str) -> str | None:
    """Run `vcgencmd <args>` and return stripped stdout, or None off-Pi."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "vcgencmd", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        return out.decode(errors="ignore").strip()
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return None


_THROTTLE_BITS = {
    0: "under-voltage", 1: "arm freq capped", 2: "currently throttled",
    3: "soft temp limit", 16: "under-voltage occurred", 17: "arm freq cap occurred",
    18: "throttling occurred", 19: "soft temp limit occurred",
}


def _decode_throttled(raw: str | None) -> tuple[str | None, str | None]:
    """Decode `vcgencmd get_throttled` output → (raw_hex, human string)."""
    if not raw or "=" not in raw:
        return None, None
    hexval = raw.split("=", 1)[1].strip()
    try:
        bits = int(hexval, 16)
    except ValueError:
        return None, None
    if bits == 0:
        return hexval, "OK"
    active = [name for bit, name in _THROTTLE_BITS.items() if bits & (1 << bit)]
    return hexval, ", ".join(active) if active else "OK"


def _parse_eq_float(text: str | None) -> float | None:
    """Pull the number out of vcgencmd 'key=12.3unit' style output."""
    if not text or "=" not in text:
        return None
    num = "".join(c for c in text.split("=", 1)[1] if c.isdigit() or c in ".-")
    try:
        return float(num) if num else None
    except ValueError:
        return None


# Order of the 6-char health-flags string in TEL / GET_STATUS (serial-protocol.md).
_HEALTH_FLAG_NAMES = ("GPS", "CMP", "BAT", "DHT", "MOT", "POD")


def _boat_health() -> dict:
    """Snapshot the Boat Pico's key health from the live PicoSerial state.

    Surfaces the operationally important boat status on the command center:
    link, battery, hull leak, motor temps, GPS/heading/speed, the decoded
    per-sensor health flags, the slow ENV sensors, and the latest alert.
    """
    t = _pico.telemetry
    e = _pico.environment
    flags = (t.health or "").ljust(6, "0")
    health_flags = {
        name: (flags[i] == "1") for i, name in enumerate(_HEALTH_FLAG_NAMES)
    }
    alert = getattr(_pico, "last_alert", None)
    alert_d = None
    if alert is not None:
        alert_d = {"severity": alert.severity, "code": alert.code, "detail": alert.detail}
    return {
        "connected": bool(getattr(_pico, "connected", False)),
        "lat": t.lat, "lon": t.lon,
        "heading": t.heading, "speed_knots": t.speed_knots,
        # Three M18 battery rails: drive (from TEL), electronics + winch
        # (from ENV v1.1). hull_left/right decoded from the TEL hull code.
        "batt_v": t.batt_v, "batt_pct": t.batt_pct,            # 3× M18 drive
        "elec_v": getattr(e, "elec_batt_v", 0.0), "elec_pct": getattr(e, "elec_batt_pct", 0),
        "winch_v": getattr(e, "winch_batt_v", 0.0), "winch_pct": getattr(e, "winch_batt_pct", 0),
        "hull": t.hull,
        "hull_left": "L!" in (t.hull or ""),
        "hull_right": "R!" in (t.hull or ""),
        "mt_left": t.mt_left, "mt_right": t.mt_right,
        "health": t.health,
        "health_flags": health_flags,
        # Two SHT41s: open air (#A) and electronics enclosure (#B).
        "air_temp": e.air_temp, "air_humidity": e.air_humidity,
        "enc_temp": getattr(e, "enc_temp", -999.0),
        "enc_humidity": getattr(e, "enc_humidity", -1.0),
        "water_temp": e.water_temp, "water_ec": e.water_ec,
        "water_light": e.water_light, "bottom_contact": e.bottom_contact,
        "alert": alert_d,
    }


async def _gather_health() -> dict:
    """Collect Pi/host health.

    Optional sources degrade to None (shown as N/A in the UI) instead of
    raising: psutil if it isn't installed, vcgencmd off a Pi. A missing source
    must never tear down /ws/health — that would make the dashboard
    reconnect-loop (open → error → close → retry).
    """
    global _net_prev
    cpu_percent = ram_used = ram_total = disk_used = disk_total = None
    swap_used = swap_total = uptime_s = proc_count = load_avg = None
    net_rx_kbps = net_tx_kbps = None
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(percpu=True)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(os.path.abspath(os.sep))
        sw = psutil.swap_memory()
        ram_used = round((vm.total - vm.available) / 1e9, 2)
        ram_total = round(vm.total / 1e9, 2)
        disk_used = round(du.used / 1e9, 2)
        disk_total = round(du.total / 1e9, 2)
        swap_used = round(sw.used / 1e9, 2)
        swap_total = round(sw.total / 1e9, 2)
        uptime_s = max(0.0, time.time() - psutil.boot_time())
        proc_count = len(psutil.pids())
        try:
            load_avg = [round(x, 2) for x in psutil.getloadavg()]
        except (OSError, AttributeError):
            load_avg = None  # not available on this platform
        net = psutil.net_io_counters()
        nowm = time.monotonic()
        if _net_prev is not None and nowm > _net_prev[2]:
            dt = nowm - _net_prev[2]
            net_tx_kbps = max(0.0, (net.bytes_sent - _net_prev[0]) / dt / 1024)
            net_rx_kbps = max(0.0, (net.bytes_recv - _net_prev[1]) / dt / 1024)
        _net_prev = (net.bytes_sent, net.bytes_recv, nowm)
    except Exception as e:  # noqa: BLE001 — psutil missing/unavailable is non-fatal
        logger.debug("psutil unavailable: %s", e)

    temp_c = _parse_eq_float(await _vcgencmd("measure_temp"))
    throttled_raw, throttled = _decode_throttled(await _vcgencmd("get_throttled"))
    clock_hz = _parse_eq_float(await _vcgencmd("measure_clock", "arm"))
    volts = {src: _parse_eq_float(await _vcgencmd("measure_volts", src))
             for src in ("core", "sdram_c", "sdram_i", "sdram_p")}
    if not any(v is not None for v in volts.values()):
        volts = None

    # Pod Pico status (reached via the Boat Pico; tracked by PodBridge).
    pod_ok = pod_leak = pod_age_s = None
    if _pod is not None:
        pod_ok = bool(getattr(_pod, "pod_ok", False))
        latest = getattr(_pod, "latest", None)
        if latest is not None:
            pod_leak = bool(latest.leak_detected)
            pod_age_s = round(max(0.0, time.time() - latest.timestamp), 1)

    # Radar-bar stepper (Pi 5 GPIO; tracked by RadarTracker). None off-Pi/sim.
    stepper_angle = stepper_state = stepper_locked = stepper_target = None
    _st = _radar or _stepper
    if _st is not None:
        try:
            ss = _st.status()
            stepper_angle = ss.get("angle")
            stepper_state = ss.get("state")
            stepper_locked = ss.get("target_locked", False)
            stepper_target = ss.get("target")   # {label, conf} of the locked target
        except Exception as e:  # noqa: BLE001 — never let a status read break health
            logger.debug("stepper status unavailable: %s", e)

    # Object being tracked by the detection overlay (highest-conf priority box).
    track = None
    if _overlay is not None:
        try:
            track = _overlay.primary_target()
        except Exception as e:  # noqa: BLE001
            logger.debug("overlay primary_target unavailable: %s", e)

    # Boat / Pico health — battery, hull, motors, GPS, decoded sensor flags, and
    # the latest alert. Pulled from the live PicoSerial state (works with the
    # simulator's MockPicoSerial too). Degrades to None if no Pico is wired.
    boat = None
    if _pico is not None:
        try:
            boat = _boat_health()
        except Exception as e:  # noqa: BLE001 — telemetry read must not break health
            logger.debug("boat health unavailable: %s", e)

    return {
        "temp_c": temp_c,
        "throttled": throttled,
        "throttled_raw": throttled_raw,
        "cpu_percent": cpu_percent,
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "swap_used_gb": swap_used,
        "swap_total_gb": swap_total,
        "uptime_s": uptime_s,
        "proc_count": proc_count,
        "load_avg": load_avg,
        "net_rx_kbps": round(net_rx_kbps, 1) if net_rx_kbps is not None else None,
        "net_tx_kbps": round(net_tx_kbps, 1) if net_tx_kbps is not None else None,
        "clock_mhz": round(clock_hz / 1e6, 1) if clock_hz else None,
        "volts": volts,
        "camera_fps": round(_cam_fps, 1) if _camera is not None else None,
        "detect_fps": _overlay.detect_fps if _overlay is not None else None,
        "detections": _overlay.detections() if _overlay is not None else None,
        "pod_ok": pod_ok,
        "pod_leak": pod_leak,
        "pod_age_s": pod_age_s,
        "stepper_angle": stepper_angle,
        "stepper_state": stepper_state,
        "stepper_target_locked": stepper_locked,
        "stepper_target": stepper_target,
        "track": track,
        "boat": boat,
        "timestamp": time.time(),
    }


@app.get("/health")
async def get_health():
    """Latest Pi 5 health snapshot. Open (no API key) like a liveness probe."""
    return _latest_health if _latest_health is not None else await _gather_health()


@app.websocket("/ws/health")
async def ws_health(ws: WebSocket):
    """Stream Pi 5 health JSON every second. Auth via ?key=<api_key>.

    A gather failure surfaces as an {"error": ...} payload and the socket stays
    open — closing it would make the dashboard reconnect-loop.
    """
    if not await auth.validate_ws(ws):
        return
    await ws.accept()
    try:
        while True:
            try:
                data = _latest_health if _latest_health is not None else await _gather_health()
            except Exception as e:  # noqa: BLE001
                data = {"error": str(e), "timestamp": time.time()}
            await ws.send_json(data)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS health error: %s", e)


# ---- Camera MJPEG (reuses the shared CameraProducer) ----

def _mjpeg_part(jpeg: bytes) -> bytes:
    return (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
            + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")


async def _mjpeg_stream(view: str = "left"):
    """Yield an MJPEG stream for the selected camera ("left" or "right").

    Placeholder frames when no producer is running. Publishes at most
    _stream_fps_cap frames/s and draws the detection overlay's latest boxes on
    each frame — on BOTH the left and right views. Detection runs on its own
    task against the LEFT frame; the same boxes (and tracking reticle) are drawn
    on the right view too, offset by the stereo disparity (there's no second
    inference — the Pi is inference-bound). If "right" is requested but no right
    camera is present we fall back to the left frame. Stream FPS and detect FPS
    stay independent.
    """
    global _cam_fps
    if _camera is None:
        while True:
            yield _mjpeg_part(_NO_CAM_JPEG)
            await asyncio.sleep(1.0)

    import cv2  # producer is running, so opencv is installed
    loop = asyncio.get_running_loop()
    queue = _camera.subscribe()
    last_pub = 0.0
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                yield _mjpeg_part(_NO_CAM_JPEG)
                continue
            # Publish-rate cap (0.9 tolerance so equal rates still publish every frame).
            now = time.monotonic()
            cap = _stream_fps_cap
            if cap and last_pub and (now - last_pub) < (1.0 / cap) * 0.9:
                continue
            # Pick the requested view; right falls back to left if absent.
            show_right = view == "right" and frame.right is not None
            img = frame.right if show_right else frame.left
            # Draw the detection overlay's boxes on whichever view is shown — both
            # left and right. Boxes are computed from the LEFT frame (no second
            # inference; the Pi is inference-bound), so on the right view they sit
            # at the same pixel coords, offset by the stereo disparity. Always
            # draw on a copy — never mutate the shared producer frame.
            if _overlay is not None and _overlay.enabled:
                img = img.copy()
                _overlay.draw(img)
            # JPEG encode is blocking and CPU-heavy at 1080p; run it off the
            # event loop so it overlaps the next capture instead of serializing
            # with it. cv2 releases the GIL during imencode, so this parallelizes.
            quality = _jpeg_quality
            ok, jpeg = await loop.run_in_executor(
                None,
                lambda i=img, q=quality: cv2.imencode(
                    ".jpg", i, [cv2.IMWRITE_JPEG_QUALITY, q]),
            )
            if not ok:
                continue
            if last_pub:
                dt = now - last_pub
                if dt > 0:
                    inst = 1.0 / dt
                    _cam_fps = inst if _cam_fps == 0 else 0.8 * _cam_fps + 0.2 * inst
            last_pub = now
            yield _mjpeg_part(jpeg.tobytes())
    finally:
        _camera.unsubscribe(queue)


@app.get("/video")
async def video(request: Request):
    """MJPEG camera stream. Auth via ?key=<api_key>.

    Select the view with ?cam=left|right (default left). The detection overlay
    boxes are drawn on both views (computed from the left frame); right falls
    back to left if no right camera is present.
    """
    if not _http_key_ok(request):
        return Response(status_code=403, content="Invalid or missing API key")
    view = request.query_params.get("cam", "left")
    if view not in ("left", "right"):
        view = "left"
    return StreamingResponse(
        _mjpeg_stream(view),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def _camera_state() -> dict:
    """Current camera/detection control state for /api/camera and the UI."""
    state = {
        "camera_present": _camera is not None,
        "right_present": bool(getattr(_camera, "has_right", False)) if _camera is not None else False,
        "jpeg_quality": _jpeg_quality,
        "stream_fps": _stream_fps_cap,
        "stream_fps_actual": round(_cam_fps, 1) if _camera is not None else None,
    }
    if _overlay is not None:
        state.update(_overlay.controls())
        state["detections"] = _overlay.detections()
    else:
        state.update({"detection_enabled": False, "model_loaded": False,
                      "detect_fps": None, "detections": None})
    return state


@app.get("/api/camera")
async def get_camera(_: str = Depends(auth.require_api_key)):
    """Camera + detection control state (FPS caps, JPEG quality, detection)."""
    return _camera_state()


@app.post("/api/camera")
async def set_camera(payload: dict, _: str = Depends(auth.require_api_key)):
    """Adjust the camera feed / detection at runtime.

    Accepts any subset of: jpeg_quality (20-95), stream_fps (1-60),
    detection_enabled (bool), detect_max_fps (0.5-30), conf (0.05-0.95),
    imgsz (160-640), track_class (class label to lock onto, "" = auto).
    Capture resolution / device / camera FPS are set in config.yaml (restart).
    """
    global _jpeg_quality, _stream_fps_cap
    if "jpeg_quality" in payload:
        try:
            _jpeg_quality = max(20, min(95, int(payload["jpeg_quality"])))
        except (TypeError, ValueError):
            pass
    if "stream_fps" in payload:
        try:
            _stream_fps_cap = max(1.0, min(60.0, float(payload["stream_fps"])))
        except (TypeError, ValueError):
            pass
    if _overlay is not None:
        _overlay.apply_controls(payload)
    # Keep the radar bar tracking the same class the operator picked for vision.
    if "track_class" in payload and _radar is not None:
        try:
            _radar.set_track_class(payload["track_class"])
        except Exception:  # noqa: BLE001 — never let the UI control 500
            pass
    return _camera_state()


# ---- Radar-bar stepper (Pi 5 GPIO, via RadarTracker) ----
# Commands only flip flags on the tracker; the tracker's own daemon thread does
# the (blocking) stepping, so these handlers never stall the event loop. The
# stepper lives on the Pi 5 40-pin header — the one place this project uses Pi 5
# GPIO directly (everything else is USB). Absent off-Pi / in sim → available:false.

_STEPPER_COMMANDS = ("SCAN", "STOP", "GOTO", "JOG", "CENTER", "SLEEP", "WAKE", "TRACK", "HOLD")


def _stepper_iface():
    """The active stepper interface: prefer the tracker, fall back to raw."""
    return _radar or _stepper


@app.get("/stepper/status")
async def stepper_status(_: str = Depends(auth.require_api_key)):
    """Current radar-bar angle / mode / lock state."""
    iface = _stepper_iface()
    if iface is None:
        return {"available": False, "angle": None, "state": None,
                "target_locked": False}
    try:
        return iface.status()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)}


@app.post("/stepper/command")
async def stepper_command(payload: dict, _: str = Depends(auth.require_api_key)):
    """Drive the radar bar. Body: {"command": <cmd>, "value": <degrees>}.

    Commands: SCAN | STOP | GOTO | JOG | CENTER | SLEEP | WAKE | TRACK | HOLD.
    GOTO takes an absolute angle; JOG a signed relative pan (+ = right/CW,
    - = left/CCW). Both are clamped to the bar's travel limits.
    """
    cmd = str(payload.get("command", "")).upper()
    if cmd not in _STEPPER_COMMANDS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400,
                            detail="command must be one of %s" % (_STEPPER_COMMANDS,))
    if _radar is None:
        return {"ok": False, "error": "stepper/radar tracker not running (hardware-only)"}
    try:
        if cmd == "GOTO":
            val = payload.get("value")
            if val is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="GOTO needs 'value' (degrees)")
            _radar.goto(float(val))
        elif cmd == "JOG":
            val = payload.get("value")
            if val is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="JOG needs 'value' (signed degrees)")
            _radar.jog(float(val))
        elif cmd == "CENTER":
            _radar.center()
        elif cmd == "WAKE":
            _radar.wake()
        elif cmd == "STOP":
            _radar.set_mode("HOLD")
        else:  # SCAN | TRACK | HOLD | SLEEP
            _radar.set_mode(cmd)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "command": cmd, "status": _radar.status()}


# ---- Pico terminal (parsed-frame monitor + command sender + reflash) ----

def _pico_status_lines(state: dict) -> list[str]:
    """Build human-readable lines from the latest parsed Pico state.

    `state` is a dict the caller persists between calls so a line is emitted
    only when something changes or a throttle interval elapses.
    """
    lines: list[str] = []
    now = time.monotonic()

    if _pico is None:
        if not state.get("warned"):
            state["warned"] = True
            lines.append("ERROR: no Pico interface configured")
        return lines

    connected = bool(getattr(_pico, "connected", False))
    if connected != state.get("connected"):
        state["connected"] = connected
        lines.append("PICO: link UP" if connected
                     else "ERROR: PICO NOT CONNECTED — retrying")
    if not connected:
        return lines

    if now - state.get("tel_t", 0.0) >= 1.0:
        state["tel_t"] = now
        t = _pico.telemetry
        lines.append(
            "PICO:TEL lat=%.6f lon=%.6f hdg=%.1f spd=%.1fkn batt=%.1fV(%d%%) "
            "hull=%s L=%.0f R=%.0f health=%s" % (
                t.lat, t.lon, t.heading, t.speed_knots, t.batt_v, t.batt_pct,
                t.hull, t.mt_left, t.mt_right, t.health))

    if now - state.get("env_t", 0.0) >= 5.0:
        state["env_t"] = now
        e = _pico.environment
        lines.append(
            "PICO:ENV air=%d°C/%d%% water=%.1f°C ec=%.0f light=%d bottom=%s" % (
                e.air_temp, e.air_humidity, e.water_temp, e.water_ec,
                e.water_light, "YES" if e.bottom_contact else "no"))

    alert = getattr(_pico, "last_alert", None)
    if alert is not None:
        sig = (alert.severity, alert.code, alert.detail)
        if sig != state.get("alert_sig"):
            state["alert_sig"] = sig
            high = alert.severity.upper() in ("CRIT", "CRITICAL", "ERROR")
            prefix = "ERROR:" if high else "PICO:ALERT"
            lines.append("%s [%s] %s %s" % (prefix, alert.severity, alert.code, alert.detail))

    return lines


# Terminal command name → PicoSerial coroutine. Args are positional strings.
_PICO_COMMANDS = {
    "SET_THR": lambda p, a: p.set_throttle(int(a[0]), int(a[1])),
    "SET_WINCH": lambda p, a: p.set_winch(int(a[0])),
    "SET_HDG": lambda p, a: p.set_heading(float(a[0])),
    "ESTOP": lambda p, a: p.emergency_stop(),
    "RESUME": lambda p, a: p.resume(),
    "HB": lambda p, a: p.send_heartbeat(),
    "GET_STATUS": lambda p, a: p.get_status(),
    "REQ_TEL": lambda p, a: p.request_telemetry(),
    "POLL_POD": lambda p, a: p.poll_pod(),
}


async def _run_pico_command(text: str) -> str:
    """Parse a terminal line and dispatch it to the Pico over the live link."""
    parts = text.strip().split()
    if not parts:
        return "ERROR: empty command"
    cmd = parts[0].upper()
    fn = _PICO_COMMANDS.get(cmd)
    if fn is None:
        return "ERROR: unknown command '%s' (try: %s)" % (
            cmd, ", ".join(sorted(_PICO_COMMANDS)))
    if _pico is None:
        return "ERROR: no Pico interface"
    try:
        result = await fn(_pico, parts[1:])
    except (IndexError, ValueError):
        return "ERROR: bad arguments for %s" % cmd
    except AttributeError:
        return "ERROR: %s not supported in this mode" % cmd
    except Exception as e:  # noqa: BLE001 — surface any link error to the operator
        return "ERROR: %s failed: %s" % (cmd, e)
    return "PICO: %s → %s" % (cmd, getattr(result, "msg_type", "OK"))


@app.websocket("/ws/pico")
async def ws_pico(ws: WebSocket):
    """Bidirectional Pico terminal.

    Down: human-readable lines built from *parsed* frames (TEL/ENV/ALERT) on the
    existing PicoSerial — no second serial reader is opened. Up: text commands
    dispatched to the Pico. Auth via ?key=<api_key>.
    """
    if not await auth.validate_ws(ws):
        return
    await ws.accept()

    out_q: asyncio.Queue[dict] = asyncio.Queue()

    async def pump():
        # Single writer task — avoids concurrent sends on one socket.
        state: dict = {}
        while True:
            while not out_q.empty():
                await ws.send_json(out_q.get_nowait())
            for line in _pico_status_lines(state):
                await ws.send_json({"line": line, "ts": time.time()})
            await asyncio.sleep(0.4)

    writer = asyncio.create_task(pump())
    try:
        while True:
            text = await ws.receive_text()
            out_q.put_nowait({"line": "> " + text, "ts": time.time(), "echo": True})
            out_q.put_nowait({"line": await _run_pico_command(text), "ts": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS pico error: %s", e)
    finally:
        writer.cancel()


def _pico_reflash_available() -> tuple[bool, str]:
    if _sim is not None:
        return False, "Firmware push is hardware-only (simulator is running)"
    if shutil.which("mpremote") is None:
        return False, "mpremote is not installed on this host"
    if _pico is None:
        return False, "No Pico interface configured"
    return True, ""


@app.get("/pico/files")
async def pico_files(_: str = Depends(auth.require_api_key)):
    """List files on the Pico via mpremote. Hardware-only."""
    ok, reason = _pico_reflash_available()
    if not ok:
        return {"available": False, "files": [], "reason": reason}
    port = getattr(_pico, "_port", "/dev/ttyACM0")
    was_connected = bool(getattr(_pico, "connected", False))
    if was_connected:
        await _pico.disconnect()
    try:
        rc, out = await _mpremote(port, "fs", "ls")
    finally:
        if was_connected:
            await _reconnect_pico()
    if not rc:
        return {"available": True, "files": [], "reason": out}
    files = []
    for line in out.splitlines():
        name = line.strip().split(" ")[-1]
        if name and name not in (".", ".."):
            files.append(name.lstrip(":"))
    return {"available": True, "files": files}


@app.get("/pico/file")
async def pico_file(name: str = "main.py", _: str = Depends(auth.require_api_key)):
    """Read a file off the Pico (mpremote cat) so the operator can see what's
    actually running on it. Hardware-only; briefly releases the serial link
    (same handoff as /pico/files)."""
    if "/" in name or "\\" in name or ".." in name:
        return Response(status_code=400, content="invalid filename")
    ok, reason = _pico_reflash_available()
    if not ok:
        return {"available": False, "name": name, "content": "", "reason": reason}
    port = getattr(_pico, "_port", "/dev/ttyACM0")
    was_connected = bool(getattr(_pico, "connected", False))
    if was_connected:
        await _pico.disconnect()
    try:
        rc, out = await _mpremote(port, "fs", "cat", ":" + name)
    finally:
        if was_connected:
            await _reconnect_pico()
    if not rc:
        return {"available": True, "name": name, "content": "", "reason": out}
    return {"available": True, "name": name, "content": out}


@app.post("/pico/push")
async def pico_push(payload: dict, force: bool = False,
                    _: str = Depends(auth.require_api_key)):
    """Copy a Python file to the Pico and reset it. Hardware-only.

    Releases the serial port (stopping heartbeats — the Pico's watchdog ESTOPs,
    which is the safe state), runs mpremote, then re-acquires the port. Refuses
    while a mission is running unless force=true.
    """
    content = payload.get("content")
    filename = payload.get("filename", "main.py")
    if content is None:
        return Response(status_code=400, content="missing 'content'")
    if "/" in filename or "\\" in filename or ".." in filename:
        return Response(status_code=400, content="invalid filename")

    ok, reason = _pico_reflash_available()
    if not ok:
        return {"ok": False, "error": reason}
    if (_mission is not None and getattr(_mission.state, "running", False)
            and not force):
        return {"ok": False,
                "error": "Mission running — refusing to reflash (pass force=true)"}

    port = getattr(_pico, "_port", "/dev/ttyACM0")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
    try:
        tmp.write(content)
        tmp.close()
        await _pico.disconnect()
        try:
            cp_ok, cp_msg = await _mpremote(port, "fs", "cp", tmp.name, ":" + filename)
            if not cp_ok:
                return {"ok": False, "error": "copy failed: " + cp_msg}
            rst_ok, rst_msg = await _mpremote(port, "reset")
        finally:
            await _reconnect_pico()
        if not rst_ok:
            return {"ok": False, "error": "reset failed: " + rst_msg}
        return {"ok": True, "message": "pushed %s and reset Pico" % filename}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


async def _mpremote(port: str, *args: str) -> tuple[bool, str]:
    """Run an mpremote subcommand; return (success, stderr-or-stdout)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "mpremote", "connect", port, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except (asyncio.TimeoutError, OSError) as e:
        return False, str(e)
    msg = (err or out).decode(errors="ignore").strip()
    return proc.returncode == 0, msg


async def _reconnect_pico() -> None:
    """Re-open the serial link after an mpremote operation (hardware path)."""
    if _pico is None:
        return
    try:
        await _pico.connect()
        if hasattr(_pico, "start_heartbeat"):
            await _pico.start_heartbeat()
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to reconnect to Pico after reflash: %s", e)


# ---- Health background task lifecycle ----

@app.on_event("startup")
async def _start_health_loop():
    global _health_task

    async def _loop():
        global _latest_health
        while True:
            try:
                _latest_health = await _gather_health()
            except Exception as e:  # noqa: BLE001
                logger.debug("health gather failed: %s", e)
            await asyncio.sleep(1.0)

    _health_task = asyncio.create_task(_loop())


@app.on_event("shutdown")
async def _stop_health_loop():
    if _health_task is not None:
        _health_task.cancel()
