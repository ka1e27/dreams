#!/usr/bin/env python3
"""Upload the Boat Pico firmware over USB and reset it.

Copies every ``firmware/boat-pico/*.py`` onto the Pico's filesystem with
mpremote, then resets it so the new code runs. Called automatically at Pi
boot (run_hardware.py / pi5/services/dreams.service) and runnable by hand:

    python pi5/scripts/deploy_pico.py                  # port from config.yaml
    python pi5/scripts/deploy_pico.py --port /dev/ttyACM0
    python pi5/scripts/deploy_pico.py --no-reset

Requires ``mpremote`` (``pip install mpremote``) and that no other process
(run_hardware.py, Thonny, another mpremote) is holding the serial port — only
one process can own it at a time.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a project dep, but be safe
    yaml = None

logger = logging.getLogger("deploy_pico")

REPO = Path(__file__).resolve().parents[2]          # repo root
FIRMWARE_DIR = REPO / "firmware" / "boat-pico"
CONFIG_PATH = REPO / "pi5" / "config.yaml"

# Invoke mpremote via the current interpreter (`python -m mpremote`) rather than
# the bare `mpremote` console script — the latter isn't on PATH under systemd.
_MPREMOTE = [sys.executable, "-m", "mpremote"]


def _default_port() -> str:
    """Read serial.port from config.yaml, falling back to /dev/ttyACM0."""
    if yaml is not None and CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("serial", {}).get("port", "/dev/ttyACM0")
        except Exception as e:  # noqa: BLE001
            logger.debug("config read failed: %s", e)
    return "/dev/ttyACM0"


def _request_repl(port: str, baud: int = 115200) -> None:
    """Ask a running firmware to drop to the REPL so mpremote can take the port.

    Writes a ``$REFLASH,0*<xor>`` frame over raw serial and waits for the
    firmware to exit its async loop. Best-effort and harmless if nothing is
    listening (e.g. the Pico is already at a fresh REPL, or runs older firmware
    that doesn't know REFLASH — it just NAKs and keeps running, and the copy
    below will report the usual 'could not enter raw repl' until the
    REFLASH-aware firmware is flashed once by hand).
    """
    payload = "REFLASH,0"
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    frame = ("$%s*%d\n" % (payload, cs)).encode()
    try:
        import serial  # pyserial (dependency of pyserial-asyncio)
    except ImportError:
        logger.warning("pyserial not available — skipping REPL request")
        return
    try:
        with serial.Serial(port, baud, timeout=1) as s:
            s.write(frame)
            s.flush()
        logger.info("Sent REFLASH — waiting for firmware to drop to REPL…")
        time.sleep(1.5)
    except Exception as e:  # noqa: BLE001 — best-effort; try mpremote regardless
        logger.warning("REPL request failed (%s) — trying mpremote anyway", e)


def _run(args: list[str], timeout: float = 60.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "mpremote not found — run `pip install mpremote`"
    except subprocess.TimeoutExpired:
        return False, "mpremote timed out"
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def deploy(port: str, reset: bool = True) -> bool:
    """Copy all firmware ``*.py`` to the Pico and optionally reset it.

    Returns True on success. Tries one batch copy, then falls back to
    copying file-by-file if the batch form isn't supported by the installed
    mpremote.
    """
    files = sorted(FIRMWARE_DIR.glob("*.py"))
    if not files:
        logger.error("No .py files found in %s", FIRMWARE_DIR)
        return False

    logger.info("Deploying %d firmware files to Pico on %s", len(files), port)
    # Ask any running firmware to drop to the REPL first, so mpremote can take
    # the USB-CDC port (the firmware otherwise consumes the bytes mpremote needs).
    _request_repl(port)
    ok, msg = _run([*_MPREMOTE, "connect", port, "fs", "cp", *map(str, files), ":"])
    if not ok:
        logger.warning("Batch copy failed (%s) — retrying file-by-file", msg)
        for f in files:
            ok, msg = _run([*_MPREMOTE, "connect", port, "fs", "cp", str(f), ":" + f.name])
            if not ok:
                logger.error("Copy %s failed: %s", f.name, msg)
                return False
            logger.info("  copied %s", f.name)
    else:
        for f in files:
            logger.info("  copied %s", f.name)

    if reset:
        ok, msg = _run([*_MPREMOTE, "connect", port, "reset"])
        if not ok:
            logger.error("Reset failed: %s", msg)
            return False
        logger.info("Pico reset — new firmware running")
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)-5s %(name)s — %(message)s")
    ap = argparse.ArgumentParser(description="Upload Boat Pico firmware via mpremote")
    ap.add_argument("--port", default=None,
                    help="serial port (default: config.yaml serial.port or /dev/ttyACM0)")
    ap.add_argument("--no-reset", action="store_true",
                    help="copy files but don't reset the Pico afterwards")
    args = ap.parse_args()
    port = args.port or _default_port()
    return 0 if deploy(port, reset=not args.no_reset) else 1


if __name__ == "__main__":
    sys.exit(main())
