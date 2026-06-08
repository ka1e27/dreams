"""Run the boat stack on real hardware — Pi 5 + Boat Pico + USB camera(s).

This is the hardware counterpart to run_sim.py. It wires a *real*:
  * PicoSerial  — USB CDC link to the Boat Pico (/dev/ttyACM0), with heartbeat
  * CameraProducer — USB camera(s); left required, right optional (stereo)
into the FastAPI app, then serves the dashboard (/) and command center
(/command). Use this on the Pi; use run_sim.py on a laptop with no hardware.

    python run_hardware.py

Reads pi5/config.yaml for the serial port, camera, and server settings
(falls back to sane defaults if a key is missing). Degrades gracefully:
if the camera or Pico can't be opened it logs and keeps serving so the
rest of the dashboard still works.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn
import yaml

import pi5.server.app as server_app
from pi5.comms.pico_serial import PicoSerial
from pi5.comms.pod_bridge import PodBridge
from pi5.cv.camera import CameraConfig, CameraProducer
from pi5.cv.radar_tracker import RadarTracker
from pi5.cv.stepper import StepperMotor
from pi5.cv.vision_overlay import DetectionConfig, DetectionOverlay
from pi5.navigation.mission_manager import MissionManager
from pi5.navigation.navigator import Navigator
from pi5.server.app import app, configure

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
)
logger = logging.getLogger("run_hardware")

CONFIG_PATH = Path(__file__).parent / "pi5" / "config.yaml"


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("config.yaml not found at %s — using defaults", CONFIG_PATH)
        return {}


def main() -> None:
    cfg = _load_config()
    serial_cfg = cfg.get("serial", {})
    cam_cfg = cfg.get("camera", {})
    server_cfg = cfg.get("server", {})
    hb_cfg = cfg.get("heartbeat", {})
    step_cfg = cfg.get("stepper", {})

    port = serial_cfg.get("port", "/dev/ttyACM0")
    baud = serial_cfg.get("baud", 115200)

    # --- Real hardware interfaces ---
    pico = PicoSerial(port=port, baud=baud)
    nav = Navigator(pico)
    pod = PodBridge(pico)
    mission = MissionManager(pico, nav, pod)
    camera = CameraProducer(CameraConfig(
        left_device=cam_cfg.get("left_device", 0),
        right_device=cam_cfg.get("right_device", 1),
        width=cam_cfg.get("width", 640),
        height=cam_cfg.get("height", 480),
        fps=cam_cfg.get("fps", 30),
        use_mjpg=cam_cfg.get("use_mjpg", True),
    ))

    # Live YOLO detection overlay on the /video feed (configurable model).
    det_cfg = cam_cfg.get("detection", {})
    overlay = DetectionOverlay(camera, DetectionConfig(
        enabled=det_cfg.get("enabled", True),
        model=det_cfg.get("model", "yolov8n.pt"),
        imgsz=det_cfg.get("imgsz", 416),
        conf=det_cfg.get("conf", 0.40),
        detect_max_fps=det_cfg.get("detect_max_fps", 8),
        target_classes=det_cfg.get("target_classes") or [],
        highlight_classes=det_cfg.get("highlight_classes") or ["boat", "person"],
    ))

    # Radar-bar pan stepper on the Pi 5 GPIO header (the only Pi 5 GPIO use in
    # the project). Runs in mock mode if gpiozero/lgpio is missing or the pins
    # can't be claimed — so this stays harmless on a Pi without the bar wired.
    stepper = StepperMotor(
        step_pin=step_cfg.get("step_pin", 23),
        dir_pin=step_cfg.get("dir_pin", 24),
        enable_pin=step_cfg.get("enable_pin", 25),
        sleep_pin=step_cfg.get("sleep_pin", 8),
        steps_per_rev=step_cfg.get("steps_per_rev", 3200),
        max_speed_rpm=step_cfg.get("max_rpm", 10),
        auto_sleep_s=step_cfg.get("auto_sleep_seconds", 5),
        min_deg=step_cfg.get("sweep_min_degrees", 0),
        max_deg=step_cfg.get("sweep_max_degrees", 180),
        has_slip_ring=step_cfg.get("has_slip_ring", False),
    )
    radar = RadarTracker(
        stepper, overlay,
        sweep_min_deg=step_cfg.get("sweep_min_degrees", 0),
        sweep_max_deg=step_cfg.get("sweep_max_degrees", 180),
        scan_speed_rpm=step_cfg.get("scan_speed_rpm", 3),
        track_speed_rpm=step_cfg.get("track_speed_rpm", 8),
        fov_deg=step_cfg.get("fov_degrees", 75),
        frame_width=cam_cfg.get("width", 640),
        priority_classes=step_cfg.get("priority_classes") or ["boat", "person"],
        initial_mode=step_cfg.get("initial_mode", "SLEEP"),
    )

    configure(
        pico=pico,
        navigator=nav,
        mission_mgr=mission,
        pod_bridge=pod,
        home_lat=None,            # set on first GPS fix / via RTH config later
        home_lon=None,
        api_key=server_cfg.get("api_key") or os.environ.get("BOAT_API_KEY"),
        cors_origins=server_cfg.get("cors_origins"),
        simulator=None,           # hardware mode → /pico/push enabled, real serial
        camera=camera,            # real USB camera(s) → /video + /ws/camera
        overlay=overlay,          # live detection boxes on /video
        jpeg_quality=cam_cfg.get("jpeg_quality", 60),
        stream_fps=cam_cfg.get("stream_fps", 15),
        winch_mode=cfg.get("winch", {}).get("mode", "survey"),
        stepper=stepper,          # radar-bar pan (Pi 5 GPIO)
        radar=radar,              # tracker thread = the motor's motion authority
    )

    @app.on_event("startup")
    async def _startup() -> None:
        # Camera: start() spawns a capture task, so it must run inside the loop.
        try:
            camera.start()
            logger.info("Camera producer started (left=%s right=%s)",
                        camera._cfg.left_device, camera._cfg.right_device)
        except Exception as e:  # noqa: BLE001 — no camera shouldn't kill the server
            logger.error("Camera failed to start (%s) — serving without video", e)
            server_app._camera = None  # so /video shows the NO-SIGNAL placeholder

        # Detection overlay (only worth running if the camera came up).
        if server_app._camera is not None:
            try:
                await overlay.start()
                logger.info("Detection overlay started (model=%s)", overlay._cfg.model)
            except Exception as e:  # noqa: BLE001
                logger.error("Detection overlay failed to start: %s", e)
                server_app._overlay = None
        else:
            server_app._overlay = None

        # Firmware: push the latest Boat Pico code over USB and let it reboot,
        # so the Pico is running current firmware before we open the link. The
        # port must be free here — we connect to it just below.
        if serial_cfg.get("deploy_on_start", True):
            try:
                from pi5.scripts.deploy_pico import deploy
                loop = asyncio.get_event_loop()
                if await loop.run_in_executor(None, deploy, port):
                    logger.info("Pico firmware deployed; waiting for reboot…")
                    await asyncio.sleep(2.5)
                else:
                    logger.error("Pico firmware deploy failed — connecting anyway")
            except Exception as e:  # noqa: BLE001 — never block startup on deploy
                logger.error("Pico deploy step errored: %s", e)

        # Pico: connect + heartbeat. Heartbeats keep the Pico's watchdog happy;
        # if they stop, the Pico ESTOPs (the safe state).
        try:
            await pico.connect()
            await pico.start_heartbeat(interval=hb_cfg.get("interval_s", 1.0))
            logger.info("Connected to Boat Pico on %s", port)
        except Exception as e:  # noqa: BLE001 — keep serving so the UI can report it
            logger.error("Failed to connect to Boat Pico on %s: %s", port, e)

        await nav.start()
        await pod.start()

        # Radar-bar tracker owns its own daemon thread (blocking stepper pulses
        # must stay off the event loop). Never let it block startup.
        try:
            radar.start()
            logger.info("Radar tracker started (stepper mock=%s)", stepper.mock)
        except Exception as e:  # noqa: BLE001
            logger.error("Radar tracker failed to start: %s", e)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await nav.stop()
        await pod.stop()
        await pico.disconnect()
        await overlay.stop()
        await camera.stop()
        try:
            radar.stop()   # joins the tracker thread + cleans up GPIO
        except Exception as e:  # noqa: BLE001
            logger.error("Radar tracker shutdown error: %s", e)

    host = server_cfg.get("host", "0.0.0.0")
    sport = server_cfg.get("port", 8080)
    print(f"\n  Boat (HARDWARE) serving on http://{host}:{sport}")
    print(f"  Command center at         http://<pi-ip>:{sport}/command\n")
    uvicorn.run(app, host=host, port=sport)


if __name__ == "__main__":
    main()
