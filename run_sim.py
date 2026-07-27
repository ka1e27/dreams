"""Run the boat simulation locally — no hardware required.

Starts the BoatSimulator, wires up Navigator/MissionManager/PodBridge
with a MockPicoSerial, and launches the FastAPI server on port 8000.

Usage:
    python run_sim.py
"""
import asyncio
import logging
from pathlib import Path

import uvicorn

from pi5.comms.pod_bridge import PodBridge
from pi5.cv.object_memory import ObjectMemory
from pi5.cv.recorder import Recorder
from pi5.navigation.mission_manager import MissionManager
from pi5.navigation.navigator import Navigator
from pi5.navigation.sim_obstacles import ObstacleField, SimAvoider, SimObjectMapper
from pi5.navigation.simulator import BoatSimulator
from pi5.server.app import app, configure

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
)


def main():
    # Create simulator and mock hardware
    sim = BoatSimulator(start_lat=51.506726, start_lon=-0.071438)
    pico = sim.create_mock_pico()

    # Build the component stack
    nav = Navigator(pico)
    pod = PodBridge(pico)
    mission = MissionManager(pico, nav, pod)

    # Simulated obstacle field — plays the vision sensor's role from ground truth
    # so reactive avoidance runs end-to-end without a camera. Drop obstacles from
    # the command center (DROP OBSTACLE) or POST /api/sim/obstacles; the avoider
    # drives the same steer-away override the boat uses on hardware.
    obstacles = ObstacleField()
    avoider = SimAvoider(obstacles, nav)

    # Persistent object memory + a ground-truth "sensor" that feeds it, so the
    # GPS-anchored buoy/landmark map (confirm → drop marker → refine → forget)
    # runs end-to-end without a camera. Drop a "buoy" or "person" obstacle and
    # watch it get confirmed onto the command-center map.
    object_memory = ObjectMemory()
    mapper = SimObjectMapper(obstacles, object_memory)

    # Camera clip recorder + Tesla-style sentry. No camera in sim, so the feed
    # synthesises a telemetry-HUD frame — arm SENTRY or hit REC in the dashboard
    # and it writes real, playable .webm clips under pi5/server/recordings/.
    recorder = Recorder(Path(__file__).parent / "pi5" / "server" / "recordings")

    # Inject into the FastAPI app
    configure(
        pico=pico,
        navigator=nav,
        mission_mgr=mission,
        pod_bridge=pod,
        home_lat=sim.lat,
        home_lon=sim.lon,
        cors_origins=["http://localhost:5173", "http://localhost:3000"],
        simulator=sim,
        obstacle_field=obstacles,
        object_memory=object_memory,
        recorder=recorder,
    )

    avoid_task: list[asyncio.Task] = []

    async def _avoid_loop():
        # ~4 Hz, the same cadence the hardware reactive layer runs at.
        while True:
            try:
                avoiding = avoider.update(sim.lat, sim.lon, sim.heading)
                # Same tick, feed the object map from ground truth (the sim's
                # stand-in for the vision pipeline geolocating detections).
                mapper.update(sim.lat, sim.lon, sim.heading)
                # Reactive avoidance is a "critical moment" — the sim's stand-in
                # for a CRITICAL vision threat, so armed sentry auto-records it
                # (debounced inside note_event; no-op when sentry is off).
                if avoiding:
                    recorder.note_event("critical-threat:obstacle")
            except Exception as e:  # noqa: BLE001 — a glitch must not kill the loop
                logging.getLogger("run_sim").debug("sim avoid error: %s", e)
            await asyncio.sleep(0.25)

    # Start simulator and nav loop before serving
    async def on_startup():
        await sim.start()
        await nav.start()
        await pod.start()
        avoid_task.append(asyncio.create_task(_avoid_loop()))

    @app.on_event("startup")
    async def startup():
        await on_startup()

    @app.on_event("shutdown")
    async def shutdown():
        for t in avoid_task:
            t.cancel()
        await sim.stop()
        await nav.stop()
        await pod.stop()

    print("\n  Boat simulator running on http://localhost:8000")
    print("  API docs at          http://localhost:8000/docs\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
