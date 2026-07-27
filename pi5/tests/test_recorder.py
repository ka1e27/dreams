"""Tests for the camera clip recorder (manual + sentry pre-roll)."""
from __future__ import annotations

import json
import time

import numpy as np
import pytest

from pi5.cv.recorder import Recorder, RecorderConfig

pytest.importorskip("cv2")


def _frame(h: int = 72, w: int = 128) -> np.ndarray:
    return (np.random.rand(h, w, 3) * 255).astype(np.uint8)


def test_manual_clip_writes_file_and_metadata(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128))
    assert rec.start_manual(now=0.0) is not None
    for i in range(5):
        rec.add_frame(_frame(), now=0.1 * (i + 1))
    meta = rec.stop(now=0.6)

    assert meta is not None
    assert meta["trigger"] == "manual"
    assert meta["frames"] == 5
    vid = tmp_path / meta["file"]
    assert vid.exists() and vid.stat().st_size > 0
    # sidecar JSON matches
    side = json.loads((vid.with_suffix(".json")).read_text())
    assert side["name"] == meta["name"]
    clips = rec.list_clips()
    assert len(clips) == 1 and clips[0]["file"] == meta["file"]


def test_sentry_event_includes_preroll_and_autostops(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(
        fps=10, preroll_s=0.5, clip_s=0.5, width=128, sentry_default=True))

    # Warm the pre-roll ring (sentry on, no clip yet) — maxlen = 0.5*10 = 5.
    for i in range(8):
        rec.add_frame(_frame(), now=0.1 * i)
    assert rec.status()["preroll_frames"] == 5

    started = rec.note_event("critical-threat", now=0.8)
    assert started
    st = rec.status()
    assert st["recording"] and st["active_frames"] == 5   # seeded from pre-roll

    for i in range(4):
        rec.add_frame(_frame(), now=0.9 + 0.1 * i)
    # Not yet past the deadline (0.8 + 0.5 = 1.3)
    rec.tick(now=1.2)
    assert rec.status()["recording"]
    # Past the deadline -> auto-stop
    rec.tick(now=1.4)
    assert not rec.status()["recording"]

    clips = rec.list_clips()
    assert len(clips) == 1
    assert clips[0]["trigger"] == "sentry"
    assert clips[0]["severity"] == "critical"
    assert clips[0]["frames"] == 9   # 5 pre-roll + 4 live


def test_preroll_only_fills_when_sentry_enabled(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(fps=10, preroll_s=1.0, sentry_default=False))
    for i in range(5):
        rec.add_frame(_frame(), now=0.1 * i)
    assert rec.status()["preroll_frames"] == 0   # idle when sentry off
    rec.set_sentry(True)
    for i in range(5):
        rec.add_frame(_frame(), now=1.0 + 0.1 * i)
    assert rec.status()["preroll_frames"] == 5


def test_retrigger_extends_running_sentry_clip(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(
        fps=10, clip_s=0.5, retrigger_extend_s=0.5, max_clip_s=5.0,
        width=128, sentry_default=True))
    rec.add_frame(_frame(), now=0.0)
    rec.note_event("critical-threat", now=0.2)   # deadline 0.7
    rec.note_event("hull-leak", now=0.6)          # extends to 0.6+0.5 = 1.1
    rec.tick(now=0.8)
    assert rec.status()["recording"]              # would have stopped at 0.7 without extend
    rec.tick(now=1.2)
    assert not rec.status()["recording"]
    assert "critical-threat" in rec.list_clips()[0]["reason"]
    assert "hull-leak" in rec.list_clips()[0]["reason"]


def test_persistent_threat_records_until_it_clears(tmp_path):
    """A threat still in view must NOT stop the clip at max_clip_s — it rolls
    over into new segments and only stops once the threat clears."""
    rec = Recorder(tmp_path, RecorderConfig(
        fps=10, clip_s=0.3, retrigger_extend_s=0.3, max_clip_s=0.6,
        width=128, sentry_default=True))
    # Threat seen continuously for ~1.5 s — well past clip_s and the 0.6 s cap.
    t = 0.0
    while t < 1.5:
        rec.note_event("critical-threat:person", now=t)
        rec.add_frame(_frame(), now=t)
        rec.tick(now=t)
        t = round(t + 0.1, 3)
    assert rec.status()["recording"], "must still be recording while the threat is present"
    # Threat clears (last sighting was at t=1.4; trailing window is 0.3 s).
    rec.tick(now=1.5)
    assert rec.status()["recording"]            # still inside the trailing window
    rec.tick(now=1.9)
    assert not rec.status()["recording"]        # trailing window elapsed -> stopped
    clips = rec.list_clips()
    assert len(clips) >= 2, "a >max_clip_s threat should roll into multiple segments"
    assert all(c["trigger"] == "sentry" for c in clips)
    assert all(c["frames"] > 0 for c in clips)


def test_retention_prunes_to_max_clips(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128, max_clips=2))
    for _ in range(4):
        rec.start_manual()
        rec.add_frame(_frame())
        rec.stop()
    assert len(rec.list_clips()) == 2
    assert rec.status()["clip_count"] == 2


def test_prunes_clips_older_than_max_age(tmp_path):
    import os

    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128, max_age_days=14))
    for _ in range(2):
        rec.start_manual()
        rec.add_frame(_frame())
        rec.stop()
    assert len(rec.list_clips()) == 2

    # Backdate one clip to 15 days ago (metadata start + file mtimes).
    old_json = sorted(tmp_path.glob("clip-*.json"))[0]
    m = json.loads(old_json.read_text())
    m["started"] = time.time() - 15 * 86400
    old_json.write_text(json.dumps(m))
    past = time.time() - 15 * 86400
    os.utime(old_json, (past, past))
    os.utime(tmp_path / m["file"], (past, past))

    assert rec.prune_old() == 1                       # only the stale one
    files = {c["file"] for c in rec.list_clips()}
    assert m["file"] not in files and len(files) == 1
    assert not (tmp_path / m["file"]).exists()        # video gone too


def test_favorite_survives_age_and_count_pruning(tmp_path):
    import os

    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128, max_age_days=14, max_clips=1))
    rec.start_manual()
    rec.add_frame(_frame())
    fav = rec.stop()
    # Favorite it, then backdate it well past the age limit.
    assert rec.set_favorite(fav["file"], True) is not None
    jp = (tmp_path / fav["file"]).with_suffix(".json")
    past = time.time() - 100 * 86400
    m = json.loads(jp.read_text())
    m["started"] = past
    jp.write_text(json.dumps(m))
    os.utime(jp, (past, past))
    os.utime(tmp_path / fav["file"], (past, past))

    assert rec.prune_old() == 0                       # age sweep skips the favorite
    files = {c["file"] for c in rec.list_clips()}
    assert fav["file"] in files

    # A newer clip triggers the count cap (max_clips=1) — the favorite is still kept.
    rec.start_manual()
    rec.add_frame(_frame())
    rec.stop()
    files = {c["file"] for c in rec.list_clips()}
    assert fav["file"] in files                       # protected from the count cap too

    # Un-favorite → now the stale clip is eligible and gets pruned.
    rec.set_favorite(fav["file"], False)
    assert rec.prune_old() == 1
    assert fav["file"] not in {c["file"] for c in rec.list_clips()}


def test_set_favorite_rejects_unknown_and_traversal(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128))
    assert rec.set_favorite("../secret.webm", True) is None
    assert rec.set_favorite("nope.webm", True) is None


def test_max_age_zero_keeps_everything(tmp_path):
    import os

    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128, max_age_days=0))
    rec.start_manual()
    rec.add_frame(_frame())
    rec.stop()
    j = next(tmp_path.glob("clip-*.json"))
    past = time.time() - 400 * 86400
    os.utime(j, (past, past))
    assert rec.prune_old() == 0                        # 0 disables age pruning
    assert len(rec.list_clips()) == 1


def test_delete_and_path_traversal_guard(tmp_path):
    rec = Recorder(tmp_path, RecorderConfig(fps=10, width=128))
    rec.start_manual()
    rec.add_frame(_frame())
    meta = rec.stop()
    assert rec.clip_path(meta["file"]) is not None
    assert rec.clip_path("../secret.webm") is None
    assert rec.clip_path("nope.webm") is None
    assert rec.delete_clip(meta["file"]) is True
    assert rec.list_clips() == []
