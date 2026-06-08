"""Run the boat simulation locally — no hardware required.

Starts the BoatSimulator, wires up Navigator/MissionManager/PodBridge
with a MockPicoSerial, and launches the FastAPI server on port 8080.

Usage:
    python run_sim.py
"""
import logging

import uvicorn

from pi5.comms.pod_bridge import PodBridge
from pi5.navigation.mission_manager import MissionManager
from pi5.navigation.navigator import Navigator
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
    )

    # Start simulator and nav loop before serving
    async def on_startup():
        await sim.start()
        await nav.start()
        await pod.start()

    @app.on_event("startup")
    async def startup():
        await on_startup()

    @app.on_event("shutdown")
    async def shutdown():
        await sim.stop()
        await nav.stop()
        await pod.stop()

    print("\n  Boat simulator running on http://localhost:8080")
    print("  API docs at          http://localhost:8080/docs\n")

    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
