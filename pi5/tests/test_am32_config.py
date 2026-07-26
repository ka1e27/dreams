"""AM32 ESC settings library — the field registry the dashboard editor renders.

Covers decode/encode/validate/round-trip on `am32_config` (the pure logic behind
the /api/esc/read + /api/esc/write endpoints). No serial IO is exercised here.
"""

import pytest

from pi5.scripts import am32_config as a


# --------------------------------------------------------------------------- #
# decode
# --------------------------------------------------------------------------- #
def test_mock_decodes_to_full_registry():
    fields = a.decode_eeprom(a.default_mock_eeprom())
    assert len(fields) == len(a.FIELDS)
    # every field carries the descriptor the UI needs
    for d in fields:
        assert {"key", "label", "group", "kind", "editable", "display"} <= d.keys()
    # groups present and ordered as declared
    assert [g[0] for g in a.GROUPS] == ["drive", "protect", "tune", "info"]


def test_mock_known_values():
    by = {d["key"]: d for d in a.decode_eeprom(a.default_mock_eeprom())}
    assert by["name"]["value"] == "NeutronRC G0"
    assert by["firmware"]["display"] == "v2.15"
    assert by["boot"]["value"] is True and by["boot"]["display"] == "Configured"
    assert by["bidir"]["value"] is True and by["bidir"]["display"] == "ON"
    assert by["telemetry"]["value"] is True
    assert by["motor_kv"]["display"] == "2200 KV"        # raw 55 * scale 40
    assert by["poles"]["value"] == 14


def test_numeric_scaling_and_units():
    by = {d["key"]: d for d in a.decode_eeprom(a.default_mock_eeprom())}
    # LVC 3.0 V/cell = base 2.5 + raw 50 * 0.01
    assert by["lvc_cell_v"]["value"] == pytest.approx(3.0)
    assert by["lvc_cell_v"]["unit"] == "V/cell"
    assert by["lvc_cell_v"]["min"] == 2.5 and by["lvc_cell_v"]["max"] == 3.6
    # timing 15° = raw 2 * 7.5
    assert by["timing"]["value"] == pytest.approx(15.0)


# --------------------------------------------------------------------------- #
# warn flags (drive the amber UI treatment + must recompute client-side)
# --------------------------------------------------------------------------- #
def test_warn_when_emitted_for_recompute():
    by = {d["key"]: d for d in a.decode_eeprom(a.default_mock_eeprom())}
    # bidir wants ON; warn_when False is emitted so the UI can flip live
    assert by["bidir"]["warn_when"] is False
    assert by["rc_car_rev"]["warn_when"] is True


def test_bidir_off_warns_rc_car_on_warns():
    e = a.default_mock_eeprom()
    e[18] = 0        # bidir OFF — bad for the boat
    e[38] = 1        # rc car reversing ON — bad for the boat
    by = {d["key"]: d for d in a.decode_eeprom(e)}
    assert by["bidir"].get("warn") is True
    assert by["rc_car_rev"].get("warn") is True


def test_good_state_has_no_warn():
    by = {d["key"]: d for d in a.decode_eeprom(a.default_mock_eeprom())}
    assert "warn" not in by["bidir"]      # ON
    assert "warn" not in by["rc_car_rev"]  # OFF


# --------------------------------------------------------------------------- #
# encode / validate
# --------------------------------------------------------------------------- #
def test_apply_bool_and_numeric():
    buf = a.default_mock_eeprom()
    changed = a.apply_changes(buf, {"bidir": False, "lvc_cell_v": 3.2})
    assert set(changed) == {"bidir", "lvc_cell_v"}
    assert buf[18] == 0
    assert buf[37] == 70                  # (3.2 - 2.5) / 0.01
    by = {d["key"]: d for d in a.decode_eeprom(buf)}
    assert by["lvc_cell_v"]["value"] == pytest.approx(3.2)


def test_apply_noop_when_unchanged():
    buf = a.default_mock_eeprom()
    assert a.apply_changes(buf, {"bidir": True}) == []      # already ON


@pytest.mark.parametrize("truthy", ["on", "1", "true", "yes", True, 1])
def test_bool_accepts_common_truthy(truthy):
    buf = a.default_mock_eeprom()
    buf[18] = 0
    a.apply_changes(buf, {"bidir": truthy})
    assert buf[18] == 1


def test_reject_unknown_key():
    with pytest.raises(a.Am32Error, match="unknown setting"):
        a.apply_changes(a.default_mock_eeprom(), {"nope": 1})


def test_reject_readonly_key():
    with pytest.raises(a.Am32Error, match="read-only"):
        a.apply_changes(a.default_mock_eeprom(), {"name": "hax"})


def test_reject_out_of_range():
    with pytest.raises(a.Am32Error, match="≤"):
        a.apply_changes(a.default_mock_eeprom(), {"lvc_cell_v": 9.9})
    with pytest.raises(a.Am32Error, match="≥"):
        a.apply_changes(a.default_mock_eeprom(), {"lvc_cell_v": 1.0})


def test_reject_non_numeric():
    with pytest.raises(a.Am32Error, match="number"):
        a.apply_changes(a.default_mock_eeprom(), {"timing": "fast"})


def test_validation_is_all_or_nothing():
    # a bad value anywhere in the batch must not mutate the buffer at all
    buf = a.default_mock_eeprom()
    before = bytes(buf)
    with pytest.raises(a.Am32Error):
        a.apply_changes(buf, {"bidir": False, "lvc_cell_v": 99})
    assert bytes(buf) == before          # bidir change rolled back with the batch


def test_round_trip_reflects_in_decode():
    buf = a.default_mock_eeprom()
    a.apply_changes(buf, {"telemetry": False, "timing": 22.5})
    by = {d["key"]: d for d in a.decode_eeprom(buf)}
    assert by["telemetry"]["display"] == "OFF"
    assert by["timing"]["value"] == pytest.approx(22.5)


def test_numeric_clamps_to_byte_after_scaling():
    # startup power 150% is the max; raw stays a valid byte
    buf = a.default_mock_eeprom()
    a.apply_changes(buf, {"startup_pow": 150})
    assert buf[25] == 150
