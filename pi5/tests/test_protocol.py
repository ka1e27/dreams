"""Tests for serial protocol — framing, checksum, parsing, building commands."""
import pytest

from pi5.comms.protocol import ParsedFrame, build_command, checksum, frame, parse_frame


class TestChecksum:
    """Test XOR checksum calculation."""

    def test_empty_string(self):
        assert checksum("") == 0

    def test_single_char(self):
        assert checksum("A") == ord("A")

    def test_known_value(self):
        # XOR of 'P','O','L','L' = 80^79^76^76 = 80^79=31, 31^76=83, 83^76=31
        # Actually let's compute: P=80,O=79,L=76,L=76
        cs = 80 ^ 79 ^ 76 ^ 76
        assert checksum("POLL") == cs

    def test_same_char_twice_cancels(self):
        # XOR of same char twice = 0
        assert checksum("AA") == 0

    def test_pod_message(self):
        msg = "POD,18.3,4520.0,45,0"
        cs = 0
        for ch in msg:
            cs ^= ord(ch)
        assert checksum(msg) == cs


class TestFrame:
    """Test frame encoding."""

    def test_basic_frame(self):
        result = frame("HB,1")
        # Should be $HB,1*<cs>\n
        assert result.startswith(b"$")
        assert result.endswith(b"\n")
        assert b"*" in result

    def test_frame_round_trip(self):
        payload = "SET_THR,12,40,40"
        encoded = frame(payload)
        line = encoded.decode("ascii").strip()
        parsed = parse_frame(line)
        assert parsed is not None
        assert parsed.msg_type == "SET_THR"
        assert parsed.seq == 12
        assert parsed.fields == ["40", "40"]


class TestParseFrame:
    """Test frame parsing and validation."""

    def test_valid_frame(self):
        payload = "TEL,0,51.5,-0.07,185.3,1.2,15.4,92,DRY,52.1,49.3,111100"
        cs = checksum(payload)
        line = "$%s*%d" % (payload, cs)
        result = parse_frame(line)
        assert result is not None
        assert result.msg_type == "TEL"
        assert result.seq == 0
        assert result.fields[0] == "51.5"

    def test_invalid_checksum(self):
        line = "$HB,1*999"
        assert parse_frame(line) is None

    def test_no_dollar_sign(self):
        assert parse_frame("HB,1*72") is None

    def test_no_asterisk(self):
        assert parse_frame("$HB,1") is None

    def test_empty_string(self):
        assert parse_frame("") is None

    def test_whitespace_only(self):
        assert parse_frame("   ") is None

    def test_too_few_fields(self):
        # Need at least MSG_TYPE and SEQ
        payload = "HB"
        cs = checksum(payload)
        assert parse_frame("$%s*%d" % (payload, cs)) is None

    def test_non_numeric_seq(self):
        payload = "HB,abc"
        cs = checksum(payload)
        assert parse_frame("$%s*%d" % (payload, cs)) is None

    def test_ack_response(self):
        payload = "ACK,12,SET_THR,40,40"
        cs = checksum(payload)
        line = "$%s*%d" % (payload, cs)
        result = parse_frame(line)
        assert result is not None
        assert result.msg_type == "ACK"
        assert result.seq == 12
        assert result.fields == ["SET_THR", "40", "40"]

    def test_nak_response(self):
        payload = "NAK,5,SET_THR,RC_ACTIVE"
        cs = checksum(payload)
        line = "$%s*%d" % (payload, cs)
        result = parse_frame(line)
        assert result is not None
        assert result.msg_type == "NAK"
        assert result.fields == ["SET_THR", "RC_ACTIVE"]

    def test_alert_message(self):
        payload = "ALERT,0,CRIT,HB_LOST"
        cs = checksum(payload)
        line = "$%s*%d" % (payload, cs)
        result = parse_frame(line)
        assert result is not None
        assert result.msg_type == "ALERT"
        assert result.fields == ["CRIT", "HB_LOST"]

    def test_with_newline(self):
        payload = "HB,1"
        cs = checksum(payload)
        line = "$%s*%d\n" % (payload, cs)
        result = parse_frame(line)
        assert result is not None

    def test_corrupted_payload(self):
        # Valid format but wrong checksum
        assert parse_frame("$HB,1*0") is None


class TestBuildCommand:
    """Test command building."""

    def test_simple_command(self):
        result = build_command("HB", 1)
        line = result.decode("ascii").strip()
        parsed = parse_frame(line)
        assert parsed is not None
        assert parsed.msg_type == "HB"
        assert parsed.seq == 1

    def test_command_with_ints(self):
        result = build_command("SET_THR", 12, 40, -30)
        line = result.decode("ascii").strip()
        parsed = parse_frame(line)
        assert parsed is not None
        assert parsed.msg_type == "SET_THR"
        assert parsed.seq == 12
        assert parsed.fields == ["40", "-30"]

    def test_command_with_float(self):
        result = build_command("SET_HDG", 5, 185.5)
        line = result.decode("ascii").strip()
        parsed = parse_frame(line)
        assert parsed is not None
        assert parsed.fields[0] == "185.5"

    def test_round_trip_all_types(self):
        for msg_type, args in [
            ("HB", ()),
            ("SET_THR", (40, 40)),
            ("SET_WINCH", (50,)),
            ("SET_HDG", (185.5,)),
            ("ESTOP", ()),
            ("RESUME", ()),
            ("POLL_POD", ()),
            ("REQ_TEL", ()),
        ]:
            data = build_command(msg_type, 1, *args)
            line = data.decode("ascii").strip()
            parsed = parse_frame(line)
            assert parsed is not None, "Failed to parse %s" % msg_type
            assert parsed.msg_type == msg_type
