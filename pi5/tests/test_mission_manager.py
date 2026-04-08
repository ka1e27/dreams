"""Tests for MissionManager — load, validate, and mission state."""
import json
from pathlib import Path

import pytest

from pi5.navigation.mission_manager import (
    MissionManager,
    MissionPhase,
    WaypointType,
)


@pytest.fixture
def sample_mission_dict():
    """A valid mission dictionary."""
    return {
        "name": "Test Mission",
        "waypoints": [
            {"lat": 51.5082, "lon": -0.0745, "type": "path", "label": "Exit dock"},
            {"lat": 51.5082, "lon": -0.0725, "type": "data", "max_time": 120, "label": "Sample 1"},
            {"lat": 51.5079, "lon": -0.0730, "type": "data", "max_time": 60, "label": "Sample 2"},
            {"lat": 51.5080, "lon": -0.0740, "type": "path", "label": "Return"},
        ],
    }


@pytest.fixture
def waypoints_file(tmp_path, sample_mission_dict):
    """Write a waypoints.json file for testing."""
    data = {
        "home": {"lat": 51.506726, "lon": -0.071438, "name": "Dock"},
        "missions": {"test": sample_mission_dict},
    }
    path = tmp_path / "waypoints.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def manager():
    """MissionManager with no hardware (only testing load/validate logic)."""
    return MissionManager(pico=None, navigator=None, pod=None)


class TestLoadFromDict:
    """Test loading missions from dictionaries."""

    def test_valid_mission(self, manager, sample_mission_dict):
        assert manager.load_from_dict(sample_mission_dict) is True
        assert len(manager.waypoints) == 4
        assert manager.state.name == "Test Mission"
        assert manager.state.total_wps == 4

    def test_waypoint_types_parsed(self, manager, sample_mission_dict):
        manager.load_from_dict(sample_mission_dict)
        assert manager.waypoints[0].wp_type == WaypointType.PATH
        assert manager.waypoints[1].wp_type == WaypointType.DATA
        assert manager.waypoints[2].wp_type == WaypointType.DATA
        assert manager.waypoints[3].wp_type == WaypointType.PATH

    def test_max_time_parsed(self, manager, sample_mission_dict):
        manager.load_from_dict(sample_mission_dict)
        assert manager.waypoints[1].max_time_s == 120
        assert manager.waypoints[2].max_time_s == 60

    def test_default_max_time(self, manager):
        data = {
            "name": "No max_time",
            "waypoints": [{"lat": 51.5, "lon": -0.07}],
        }
        manager.load_from_dict(data)
        assert manager.waypoints[0].max_time_s == 300  # default

    def test_labels_parsed(self, manager, sample_mission_dict):
        manager.load_from_dict(sample_mission_dict)
        assert manager.waypoints[0].label == "Exit dock"
        assert manager.waypoints[1].label == "Sample 1"

    def test_empty_waypoints_fails(self, manager):
        assert manager.load_from_dict({"name": "Empty", "waypoints": []}) is False

    def test_missing_waypoints_fails(self, manager):
        assert manager.load_from_dict({"name": "No WPs"}) is False

    def test_missing_lat_fails(self, manager):
        data = {"waypoints": [{"lon": -0.07}]}
        assert manager.load_from_dict(data) is False

    def test_missing_lon_fails(self, manager):
        data = {"waypoints": [{"lat": 51.5}]}
        assert manager.load_from_dict(data) is False

    def test_invalid_lat_range(self, manager):
        data = {"waypoints": [{"lat": 91.0, "lon": -0.07}]}
        assert manager.load_from_dict(data) is False

    def test_invalid_lon_range(self, manager):
        data = {"waypoints": [{"lat": 51.5, "lon": 181.0}]}
        assert manager.load_from_dict(data) is False

    def test_negative_lat_valid(self, manager):
        data = {"waypoints": [{"lat": -33.8688, "lon": 151.2093}]}
        assert manager.load_from_dict(data) is True

    def test_default_type_is_data(self, manager):
        data = {"waypoints": [{"lat": 51.5, "lon": -0.07}]}
        manager.load_from_dict(data)
        assert manager.waypoints[0].wp_type == WaypointType.DATA

    def test_unnamed_mission(self, manager):
        data = {"waypoints": [{"lat": 51.5, "lon": -0.07}]}
        manager.load_from_dict(data)
        assert manager.state.name == "Unnamed"


class TestLoadFromFile:
    """Test loading missions from waypoints.json files."""

    def test_load_existing_mission(self, manager, waypoints_file):
        assert manager.load_waypoints_file(waypoints_file, "test") is True
        assert len(manager.waypoints) == 4

    def test_load_nonexistent_mission(self, manager, waypoints_file):
        assert manager.load_waypoints_file(waypoints_file, "nope") is False

    def test_load_nonexistent_file(self, manager, tmp_path):
        assert manager.load_waypoints_file(tmp_path / "nope.json", "test") is False

    def test_load_json_file(self, manager, tmp_path):
        mission = {
            "name": "Direct Load",
            "waypoints": [{"lat": 51.5, "lon": -0.07, "type": "data"}],
        }
        path = tmp_path / "mission.json"
        path.write_text(json.dumps(mission))
        assert manager.load_from_json(path) is True
        assert manager.state.name == "Direct Load"


class TestMissionState:
    """Test initial mission state."""

    def test_initial_state(self, manager):
        assert manager.state.running is False
        assert manager.state.paused is False
        assert manager.state.current_wp == 0
        assert manager.state.phase == MissionPhase.TRANSIT

    def test_abort_not_running(self, manager):
        # Should not raise
        manager.abort("TEST")
        assert manager.state.running is False

    def test_pause_not_running(self, manager):
        manager.pause()
        assert manager.state.paused is False  # Can't pause if not running

    def test_wp_count_after_load(self, manager, sample_mission_dict):
        manager.load_from_dict(sample_mission_dict)
        data_count = sum(1 for w in manager.waypoints if w.wp_type == WaypointType.DATA)
        path_count = sum(1 for w in manager.waypoints if w.wp_type == WaypointType.PATH)
        assert data_count == 2
        assert path_count == 2


class TestReferenceWaypoints:
    """Test loading the actual reference waypoints.json."""

    @pytest.fixture
    def ref_path(self):
        path = Path(__file__).parent.parent.parent / "reference" / "waypoints.json"
        if not path.exists():
            pytest.skip("reference/waypoints.json not found")
        return path

    def test_load_thames_east(self, manager, ref_path):
        assert manager.load_waypoints_file(ref_path, "thames_east") is True
        assert len(manager.waypoints) == 8
        # First WP is a path point
        assert manager.waypoints[0].wp_type == WaypointType.PATH
        # Third WP is a data point
        assert manager.waypoints[2].wp_type == WaypointType.DATA

    def test_load_st_k(self, manager, ref_path):
        assert manager.load_waypoints_file(ref_path, "St_k") is True
        assert len(manager.waypoints) == 7

    def test_all_coordinates_valid(self, manager, ref_path):
        for mission_key in ["thames_east", "St_k"]:
            manager.load_waypoints_file(ref_path, mission_key)
            for wp in manager.waypoints:
                assert -90 <= wp.lat <= 90
                assert -180 <= wp.lon <= 180
