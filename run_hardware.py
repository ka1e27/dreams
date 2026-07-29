"""Run the boat stack on real hardware — Pi 5 + Boat Pico + USB camera(s).

This is the hardware counterpart to run_sim.py. It wires a *real*:
  * PicoSerial  — USB CDC link to the Boat Pico (/dev/ttyACM0), with heartbeat
  * CameraProducer — USB camera(s); left required, right optional (stereo)
into the FastAPI app, then serves the command center (/) — map, telemetry,
camera, health, and controls in one page. Use this on the Pi; use
run_sim.py on a laptop with no hardware.

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
from dataclasses import fields as dc_fields
from pathlib import Path

import uvicorn
import yaml

import pi5.server.app as server_app
from pi5.comms.pico_serial import PicoSerial
from pi5.comms.pod_bridge import PodBridge
from pi5.cv.buoy_detector import BuoyDetectorConfig
from pi5.cv.camera import CameraConfig, CameraProducer
from pi5.cv.pipeline import SurveyVisionPipeline
from pi5.cv.radar_tracker import RadarTracker
from pi5.cv.recorder import Recorder, RecorderConfig
from pi5.cv.stepper import StepperMotor
from pi5.cv.vision_overlay import DetectionConfig, DetectionOverlay
from pi5.navigation.mission_manager import MissionManager
from pi5.navigation.navigator import NavConfig, Navigator
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


def _nav_config(nav_cfg: dict) -> NavConfig:
    """Build a NavConfig from the ``navigation:`` block, falling back to the
    dataclass defaults for any key that isn't set. Previously this block in
    config.yaml was silently ignored — Navigator ran on hard-coded defaults."""
    defaults = NavConfig()

    def g(key: str):
        return nav_cfg.get(key, getattr(defaults, key))

    return NavConfig(
        arrive_radius_m=float(g("arrive_radius_m")),
        hold_drift_m=float(g("hold_drift_m")),
        cruise_throttle=int(g("cruise_throttle")),
        heading_tolerance_deg=float(g("heading_tolerance_deg")),
        max_heading_error_deg=float(g("max_heading_error_deg")),
        turn_min_throttle=int(g("turn_min_throttle")),
        update_rate_hz=float(g("update_rate_hz")),
        full_speed_dist_m=float(g("full_speed_dist_m")),
        min_approach_throttle=int(g("min_approach_throttle")),
        align_speed_cut_deg=float(g("align_speed_cut_deg")),
        turn_authority_throttle=int(g("turn_authority_throttle")),
        los_enabled=bool(g("los_enabled")),
        los_lookahead_m=float(g("los_lookahead_m")),
        los_integral_gain=float(g("los_integral_gain")),
        los_integral_clamp=float(g("los_integral_clamp")),
        motor_gain_left=float(g("motor_gain_left")),
        motor_gain_right=float(g("motor_gain_right")),
        current_enabled=bool(g("current_enabled")),
        current_thrust_a=float(g("current_thrust_a")),
        current_thrust_b=float(g("current_thrust_b")),
        sk_pos_gain=float(g("sk_pos_gain")),
        sk_max_speed=float(g("sk_max_speed")),
        sk_deadband_m=float(g("sk_deadband_m")),
        sk_min_water_speed=float(g("sk_min_water_speed")),
        sk_speed_gain=float(g("sk_speed_gain")),
    )


def main() -> None:
    cfg = _load_config()
    serial_cfg = cfg.get("serial", {})
    cam_cfg = cfg.get("camera", {})
    server_cfg = cfg.get("server", {})
    hb_cfg = cfg.get("heartbeat", {})
    step_cfg = cfg.get("stepper", {})
    vision_cfg = cfg.get("vision", {})

    port = serial_cfg.get("port", "/dev/ttyACM0")
    baud = serial_cfg.get("baud", 115200)

    # --- Real hardware interfaces ---
    pico = PicoSerial(port=port, baud=baud)
    nav = Navigator(pico, _nav_config(cfg.get("navigation", {})))
    pod = PodBridge(pico)
    mission = MissionManager(pico, nav, pod)
    # Left/right device assignment: config.yaml is the default, but a live
    # reassignment from the command center (POST /api/camera/devices) is
    # persisted to pi5/server/camera_devices.json and wins on restart.
    left_dev = cam_cfg.get("left_device", 0)
    right_dev = cam_cfg.get("right_device", 2)
    dev_file = Path(__file__).parent / "pi5" / "server" / "camera_devices.json"
    try:
        import json
        saved = json.loads(dev_file.read_text(encoding="utf-8"))
        left_dev = int(saved["left_device"])
        rd = saved.get("right_device")
        right_dev = int(rd) if rd is not None else None
        logger.info("Camera assignment restored from %s (left=%s right=%s)",
                    dev_file.name, left_dev, right_dev)
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.warning("Ignoring invalid %s: %s", dev_file, e)

    camera = CameraProducer(CameraConfig(
        left_device=left_dev,
        right_device=right_dev,
        width=cam_cfg.get("width", 640),
        height=cam_cfg.get("height", 480),
        fps=cam_cfg.get("fps", 30),
        fourcc=cam_cfg.get("fourcc", "MJPG"),
        reconnect_interval_s=cam_cfg.get("reconnect_interval_s", 2.0),
    ))

    # Stereo distance for the detection overlay — adds "Xm" to each detected
    # object's label. Optional: only active if a right camera is configured
    # AND pi5/cv/calibration.npz exists (run pi5/scripts/calibrate_stereo.py
    # to generate it). Missing either just leaves distance off, no crash.
    stereo_depth = None
    if right_dev is not None:
        try:
            from pi5.cv.stereo import StereoDepth, load_calibration
            calib_path = cam_cfg.get("calibration_path", "pi5/cv/calibration.npz")
            calib = load_calibration(calib_path)
            if calib is not None:
                # SGBM at full 1080p dominates the inference budget; run it at
                # a downscaled resolution (metrically corrected) for a big FPS
                # win. Tune via camera.stereo_downscale (1.0 = full res).
                stereo_depth = StereoDepth(
                    calib, downscale=float(cam_cfg.get("stereo_downscale", 0.5)),
                    wls=bool(cam_cfg.get("stereo_wls", False)))
                logger.info("Stereo distance enabled (calibration: %s, downscale=%.2f, wls=%s)",
                            calib_path, float(cam_cfg.get("stereo_downscale", 0.5)),
                            bool(cam_cfg.get("stereo_wls", False)))
            else:
                logger.info("No stereo calibration at %s — detection boxes show no distance",
                            calib_path)
        except Exception as e:  # noqa: BLE001 — distance is a nice-to-have, never block startup
            logger.warning("Stereo distance unavailable: %s", e)

    # Live YOLO detection overlay on the /video feed (configurable model).
    det_cfg = cam_cfg.get("detection", {})
    # Classical buoy screen — only the keys BuoyDetectorConfig actually declares,
    # so a typo in config.yaml fails loudly here instead of being ignored.
    buoy_raw = det_cfg.get("buoy") or {}
    buoy_fields = {f.name for f in dc_fields(BuoyDetectorConfig)}
    unknown = set(buoy_raw) - buoy_fields
    if unknown:
        logger.warning("Ignoring unknown camera.detection.buoy keys: %s",
                       ", ".join(sorted(unknown)))
    buoy_cfg = BuoyDetectorConfig(**{k: v for k, v in buoy_raw.items()
                                     if k in buoy_fields})
    overlay = DetectionOverlay(camera, DetectionConfig(
        enabled=det_cfg.get("enabled", True),
        model=det_cfg.get("model", "yolov8n.pt"),
        imgsz=det_cfg.get("imgsz", 416),
        conf=det_cfg.get("conf", 0.40),
        detect_max_fps=det_cfg.get("detect_max_fps", 8),
        target_classes=det_cfg.get("target_classes") or [],
        highlight_classes=det_cfg.get("highlight_classes") or ["boat", "person"],
        track_class=det_cfg.get("track_class", "") or "",
        class_conf=det_cfg.get("class_conf") or {},
        num_threads=int(det_cfg.get("num_threads", 0) or 0),
        buoy_fallback=buoy_cfg.enabled,
        buoy_cfg=buoy_cfg,
    ), stereo=stereo_depth)

    # Radar-bar pan stepper on the Pi 5 GPIO header (the only Pi 5 GPIO use in
    # the project). Runs in mock mode if gpiozero/lgpio is missing or the pins
    # can't be claimed — so this stays harmless on a Pi without the bar wired.
    stepper = StepperMotor(
        step_pin=step_cfg.get("step_pin", 23),
        dir_pin=step_cfg.get("dir_pin", 24),
        enable_pin=step_cfg.get("enable_pin", 25),
        sleep_pin=step_cfg.get("sleep_pin", 8),
        reset_pin=step_cfg.get("reset_pin", None),  # None = RESET jumpered to SLEEP
        steps_per_rev=step_cfg.get("steps_per_rev", 400),
        max_speed_rpm=step_cfg.get("max_rpm", 10),
        auto_sleep_s=step_cfg.get("auto_sleep_seconds", 5),
        # Travel limits = the MANUAL pan range (full 0–360 by default); the
        # auto-scan SCAN sweep is the narrower sweep_* range passed to the
        # RadarTracker below. has_slip_ring only governs 0°/360° wrapping.
        min_deg=step_cfg.get("manual_min_degrees", 0),
        max_deg=step_cfg.get("manual_max_degrees", 360),
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

    # Three-tier survey vision pipeline. LAYERS on the overlay + radar above (it
    # does NOT run a second YOLO): Tier 1 water segmentation gates the existing
    # detection overlay, Tier 3 threat assessment drives the radar. Runs even
    # without a segmentation model (classical CV fallback) — the only hard
    # requirement is the camera producer.
    pipeline = SurveyVisionPipeline(
        camera, overlay=overlay, radar=radar,
        config=vision_cfg, pico=pico, navigator=nav,
        fov_deg=step_cfg.get("fov_degrees", 75),
        frame_width=cam_cfg.get("width", 640),
    )

    # Camera clip recorder + Tesla-style sentry (writes .webm to disk on the Pi).
    rec_cfg = cfg.get("recording", {}) or {}
    recorder = Recorder(
        rec_cfg.get("dir") or (Path(__file__).parent / "pi5" / "server" / "recordings"),
        RecorderConfig(
            fps=float(rec_cfg.get("fps", 10)),
            preroll_s=float(rec_cfg.get("preroll_s", 6)),
            clip_s=float(rec_cfg.get("clip_s", 12)),
            max_clip_s=float(rec_cfg.get("max_clip_s", 300)),
            retrigger_extend_s=float(rec_cfg.get("retrigger_extend_s", 8)),
            width=int(rec_cfg.get("width", 640)),
            max_clips=int(rec_cfg.get("max_clips", 60)),
            max_age_days=float(rec_cfg.get("max_age_days", 14)),
            sentry_default=bool(rec_cfg.get("sentry_default", False)),
        ),
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
        stream_fps=cam_cfg.get("stream_fps", 30),
        winch_mode=cfg.get("winch", {}).get("mode", "survey"),
        stepper=stepper,          # radar-bar pan (Pi 5 GPIO)
        radar=radar,              # tracker thread = the motor's motion authority
        pipeline=pipeline,        # three-tier vision (Tier-1 seg → threat → radar)
        recorder=recorder,        # manual + sentry camera clips → pi5/server/recordings/
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

            # Vision pipeline rides on the camera + overlay; start it once they're up.
            try:
                await pipeline.start()
                logger.info("Vision pipeline started (seg backend=%s)",
                            pipeline.seg.backend)
            except Exception as e:  # noqa: BLE001
                logger.error("Vision pipeline failed to start: %s", e)
                server_app._pipeline = None
        else:
            server_app._overlay = None
            server_app._pipeline = None

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
        try:
            await pipeline.stop()
        except Exception as e:  # noqa: BLE001
            logger.error("Vision pipeline shutdown error: %s", e)
        await overlay.stop()
        await camera.stop()
        try:
            radar.stop()   # joins the tracker thread + cleans up GPIO
        except Exception as e:  # noqa: BLE001
            logger.error("Radar tracker shutdown error: %s", e)

    host = server_cfg.get("host", "0.0.0.0")
    sport = server_cfg.get("port", 8000)
    print(f"\n  Boat (HARDWARE) serving on http://{host}:{sport}")
    print(f"  Command center at         http://<pi-ip>:{sport}/\n")
    uvicorn.run(app, host=host, port=sport)


if __name__ == "__main__":
    main()
