"""How many cores neural inference is allowed to take on the Pi 5.

Both inference backends (``ncnn_detector``, ``onnx_detector`` via ``ort_utils``)
used to pin themselves to **all four** Pi 5 cores. That is the wrong default for
this boat, for two measured reasons.

**1. It buys almost nothing.** Measured on the bench Pi 5, yolov8n @ imgsz 320
through NCNN, median of 15 runs per setting:

===========  ==========  ======  =============
threads      latency     fps     vs 1 thread
===========  ==========  ======  =============
1            27.9 ms     35.9    --
2            18.4 ms     54.3    x1.51
3            19.2 ms     52.1    x1.45
4            17.7 ms     56.6    x1.58
===========  ==========  ======  =============

Thread 2 delivers essentially all of the available speed-up; threads 3 and 4 add
~4% between them. And the detector is rate-capped at ``detect_max_fps`` (15 Hz =
a 66.7 ms budget), so even a *single* thread clears the cap with 2.4x headroom.
The extra threads are spent on latency nobody consumes.

**2. It costs power and starves everything else.** During that sweep the Pi's
sticky throttle flags went from ``0x0`` to ``0x50000`` — *under-voltage occurred*
plus *throttling occurred* — with the 4-thread pass being the peak draw. A Pi 5
needs 5 A/25 W; on a marginal supply (bench USB, or the boat's M18 -> 5 V UBEC
feeding the same rail as two USB cameras) a 4-core inference burst is what tips it
into the PMIC's undervoltage cutoff. That is the documented cause of this project's
power-off incidents (see the 2026-07-27 session journal entry). Meanwhile the Pi
concurrently runs the 15 fps Tier-1 water screen, stereo disparity, JPEG encoding,
the nav loop and the FastAPI server — all of which want a core.

So the default leaves headroom instead of chasing the last 4%. Override per
deployment with ``camera.detection.num_threads`` when you know the power budget
(e.g. a bench Pi on a real 27 W PSU with the boat stack stopped).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Cores to keep free for the rest of the stack (water screen, stereo, encode,
# nav, server). 2 leaves half the Pi 5 for everything that isn't the detector.
_RESERVED_CORES = 2
# Never hand inference more than this regardless of core count — past ~2 threads
# the measured return is inside the noise for yolov8n @ 320.
_MAX_THREADS = 4


def inference_threads(requested: int | None = None) -> int:
    """Thread count for a CPU inference session.

    ``requested`` > 0 wins (an explicit operator choice, clamped to the core
    count). ``None`` or 0 means auto: total cores minus the reserve, floored at 1.
    """
    cores = os.cpu_count() or 4
    if requested:
        try:
            n = int(requested)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return max(1, min(cores, n))
    return max(1, min(_MAX_THREADS, cores - _RESERVED_CORES))
