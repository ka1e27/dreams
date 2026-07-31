"""Tests for the Pi-side NMEA GPS reader and the PicoSerial position override.

The sentences below are real captures from the bench u-blox M10 on 2026-07-29
(/dev/ttyAMA0 @ 38400), so the checksums are genuine rather than hand-computed.
"""

import time

from pi5.comms.gps_nmea import (
    DEFAULT_BAUD,
    GpsFix,
    NmeaGps,
    NmeaParser,
    checksum_ok,
    dm_to_deg,
)
from pi5.comms.pico_serial import PicoSerial, Telemetry
from pi5.comms.protocol import frame, parse_frame

# --- Real bench captures (verbatim, checksums included) --------------------
GGA = "$GNGGA,014740.00,3734.36885,N,12223.50882,W,1,06,1.43,173.4,M,-30.0,M,,*7D"
RMC = "$GNRMC,014740.00,A,3734.36885,N,12223.50882,W,0.349,,300726,,,A,V*0A"
GSV = "$GPGSV,2,1,08,03,24,171,22,04,65,077,19,06,09,265,06,07,54,274,37,1*69"
GSA = "$GNGSA,A,3,03,09,04,07,30,16,,,,,,,2.64,1.43,2.22,1*08"

# Second capture, 2026-07-30, module indoors with no lock — the state that made
# the whole `pi-nofix` distinction necessary. Two GPS satellites audible (SNR 24
# and 30) with blank elevation/azimuth (no almanac yet, i.e. a cold start), and
# the other three constellations reporting nothing at all.
GGA_NOLOCK = "$GNGGA,213321.00,,,,,0,00,99.99,,,,,,*78"
RMC_NOLOCK = "$GNRMC,213321.00,V,,,,,,,300726,,,N,V*19"
GSV_GP_2SAT = "$GPGSV,1,1,02,03,,,24,04,,,30,1*64"
GSV_GA_EMPTY = "$GAGSV,1,1,00,0*74"
GSV_GB_EMPTY = "$GBGSV,1,1,00,0*77"
GSV_GQ_EMPTY = "$GQGSV,1,1,00,0*64"
NOLOCK_CYCLE = (GGA_NOLOCK, RMC_NOLOCK, GSV_GP_2SAT,
                GSV_GA_EMPTY, GSV_GB_EMPTY, GSV_GQ_EMPTY)

# Decimal degrees the two position sentences above must decode to.
LAT = 37.5728141667
LON = -122.3918136667


def _cksum(body: str) -> str:
    """Build a valid NMEA sentence from a body (without '$' or checksum).

    Note NMEA's checksum is **hex** (``*7D``), unlike this project's own Pico
    frame format, which uses a decimal checksum — see pi5/comms/protocol.py.
    """
    c = 0
    for ch in body:
        c ^= ord(ch)
    return "$%s*%02X" % (body, c)


# The bench module holds a fix, so a no-fix GGA can't be captured — synthesised
# with a computed checksum, in the empty-field shape u-blox emits when unlocked.
GGA_NOFIX = _cksum("GNGGA,014740.00,,,,,0,00,99.99,,,,,,")


class TestChecksum:
    def test_real_gga_passes(self):
        assert checksum_ok(GGA)

    def test_real_rmc_passes(self):
        assert checksum_ok(RMC)

    def test_corrupted_payload_fails(self):
        bad = GGA.replace("3734.36885", "3734.36886")
        assert not checksum_ok(bad)

    def test_missing_star_fails(self):
        assert not checksum_ok("$GNGGA,014740.00,3734.36885,N")

    def test_missing_dollar_fails(self):
        assert not checksum_ok("GNGGA,014740.00*7D")

    def test_non_hex_checksum_fails(self):
        assert not checksum_ok("$GNGGA,014740.00*ZZ")

    def test_empty_string_fails(self):
        assert not checksum_ok("")


class TestDmToDeg:
    def test_latitude_north(self):
        # 3734.36885 = 37 deg 34.36885 min
        assert dm_to_deg("3734.36885", "N", 90.0) == pytest_approx(LAT)

    def test_longitude_west_is_negative(self):
        # 12223.50882 = 122 deg 23.50882 min, negated for W
        assert dm_to_deg("12223.50882", "W", 180.0) == pytest_approx(LON)

    def test_south_is_negative(self):
        assert dm_to_deg("3734.36885", "S", 90.0) < 0

    def test_empty_returns_none(self):
        assert dm_to_deg("", "N", 90.0) is None

    def test_no_decimal_point_returns_none(self):
        assert dm_to_deg("3734", "N", 90.0) is None

    def test_minutes_over_60_rejected(self):
        assert dm_to_deg("3761.00000", "N", 90.0) is None

    def test_over_limit_rejected(self):
        # 9134.0 min-form would be 91.5 deg — out of range for latitude.
        assert dm_to_deg("9134.00000", "N", 90.0) is None

    def test_longitude_over_180_rejected(self):
        assert dm_to_deg("18134.00000", "E", 180.0) is None

    def test_garbage_returns_none(self):
        assert dm_to_deg("ab.cd", "N", 90.0) is None


class TestNmeaParser:
    def test_gga_yields_position(self):
        p = NmeaParser()
        fix = p.feed_line(GGA)
        assert fix is not None
        assert fix.lat == pytest_approx(LAT)
        assert fix.lon == pytest_approx(LON)
        assert fix.fix_quality == 1
        assert fix.sats == 6
        assert fix.hdop == pytest_approx(1.43)
        assert fix.altitude_m == pytest_approx(173.4)
        assert fix.has_fix

    def test_rmc_yields_speed_and_validity(self):
        p = NmeaParser()
        fix = p.feed_line(RMC)
        assert fix is not None
        assert fix.valid
        assert fix.speed_knots == pytest_approx(0.349)
        assert fix.date == "300726"
        # Empty course field must not explode — it's blank when stationary.
        assert fix.track_deg == 0.0

    def test_no_fix_gga_returns_none_but_clears_quality(self):
        p = NmeaParser()
        p.feed_line(GGA)
        assert p.fix.fix_quality == 1
        assert p.feed_line(GGA_NOFIX) is None
        assert p.fix.fix_quality == 0
        assert not p.fix.has_fix
        # Position is deliberately retained through a dropout.
        assert p.fix.lat == pytest_approx(LAT)

    def test_bad_checksum_counted_and_ignored(self):
        p = NmeaParser()
        p.feed_line(GGA.replace("173.4", "999.9"))
        assert p.bad_checksum == 1
        assert p.sentences == 0
        assert p.fix.lat == 0.0

    def test_unrelated_sentence_ignored_but_counted(self):
        p = NmeaParser()
        assert p.feed_line(GSV) is None
        assert p.sentences == 1
        assert p.position_updates == 0

    def test_position_updates_counts_only_usable(self):
        p = NmeaParser()
        p.feed_line(GGA)
        p.feed_line(RMC)
        p.feed_line(GSV)
        p.feed_line(GGA_NOFIX)
        assert p.position_updates == 2

    def test_junk_line_is_safe(self):
        p = NmeaParser()
        for junk in ("", "\x00\x00\x00", "hello", "$", "$*00", "$GN*00"):
            assert p.feed_line(junk) is None

    def test_truncated_gga_is_safe(self):
        p = NmeaParser()
        assert p.feed_line(_cksum("GNGGA,014740.00,3734.36885,N")) is None

    def test_crlf_tolerated(self):
        p = NmeaParser()
        assert p.feed_line(GGA + "\r\n") is not None

    def test_talker_agnostic(self):
        """A GPGGA must parse the same as a GNGGA."""
        p = NmeaParser()
        body = GGA[1:].partition("*")[0].replace("GNGGA", "GPGGA", 1)
        assert p.feed_line(_cksum(body)) is not None

    def test_dgps_and_rtk_qualities_accepted(self):
        for q in (2, 4, 5):
            p = NmeaParser()
            body = GGA[1:].partition("*")[0].replace(",1,06,", ",%d,06," % q, 1)
            fix = p.feed_line(_cksum(body))
            assert fix is not None and fix.fix_quality == q


class TestNmeaGps:
    def test_defaults_are_m10(self):
        g = NmeaGps()
        assert g._baud == DEFAULT_BAUD == 38400
        assert g._port == "/dev/ttyAMA0"

    def test_no_fix_before_any_data(self):
        g = NmeaGps()
        assert not g.has_fix
        assert g.age_s == float("inf")
        assert not g.connected

    def test_stats_snapshot(self):
        g = NmeaGps()
        g.parser.feed_line(GGA)
        s = g.stats()
        assert s.sentences == 1
        assert s.fix.fix_quality == 1
        assert not s.connected


# --- PicoSerial external-position override ---------------------------------

def _tel_frame(lat="0.0", lon="0.0", health="011110"):
    """Build a TEL frame like the firmware sends (lat/lon 0 with no receiver)."""
    payload = "TEL,0,%s,%s,123.4,0.0,20.1,88,DRY,35.0,36.0,%s" % (lat, lon, health)
    return parse_frame(frame(payload).decode("ascii").strip())


class TestExternalPositionOverride:
    def test_tel_alone_gives_pico_source(self):
        p = PicoSerial()
        p._handle_tel(_tel_frame())
        assert p.telemetry.lat == 0.0
        assert p.telemetry.gps_source == "pico"
        assert p.telemetry.fix_quality == 0

    def test_external_fix_overrides_tel_lat_lon(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(LAT, LON,
                                speed_knots=0.349, fix_quality=1, sats=6)
        p._handle_tel(_tel_frame())
        t = p.telemetry
        assert t.lat == pytest_approx(LAT)
        assert t.lon == pytest_approx(LON)
        assert t.speed_knots == pytest_approx(0.349)
        assert t.fix_quality == 1
        assert t.sats == 6
        assert t.gps_source == "pi"

    def test_override_survives_repeated_tel_frames(self):
        """The regression this whole mechanism exists for: _handle_tel builds a
        fresh Telemetry every second and would otherwise clobber the fix."""
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(37.5, -122.4)
        for _ in range(5):
            p._handle_tel(_tel_frame())
            assert p.telemetry.lat == pytest_approx(37.5)

    def test_fix_visible_immediately_without_waiting_for_tel(self):
        p = PicoSerial()
        p._handle_tel(_tel_frame())
        p.use_external_gps()
        p.set_external_position(37.5, -122.4)
        assert p.telemetry.lat == pytest_approx(37.5)

    def test_heading_is_never_overridden(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(37.5, -122.4)
        p._handle_tel(_tel_frame())
        assert p.telemetry.heading == pytest_approx(123.4)

    def test_health_bit0_set_when_pi_has_fix(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(37.5, -122.4, fix_quality=1)
        p._handle_tel(_tel_frame(health="011110"))
        assert p.telemetry.health == "111110"

    def test_health_bit0_cleared_when_no_fix(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(37.5, -122.4, fix_quality=0)
        p._handle_tel(_tel_frame(health="111110"))
        assert p.telemetry.health == "011110"

    def test_other_health_bits_untouched(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(37.5, -122.4, fix_quality=1)
        p._handle_tel(_tel_frame(health="000000"))
        assert p.telemetry.health[1:] == "00000"

    def test_stale_fix_keeps_position_but_drops_quality(self):
        p = PicoSerial()
        p.use_external_gps(max_age_s=0.01)
        p.set_external_position(37.5, -122.4, fix_quality=1, sats=6)
        time.sleep(0.02)
        p._handle_tel(_tel_frame())
        t = p.telemetry
        # Last known position is still served — (0, 0) would be far worse.
        assert t.lat == pytest_approx(37.5)
        assert t.fix_quality == 0
        assert t.gps_source == "pi-stale"
        assert t.health[0] == "0"

    def test_no_position_override_before_first_fix(self):
        """The Pico's TEL lat/lon survive until a real fix exists to replace them.

        `gps_source` deliberately does *not* read "pico" here any more: the Pi
        receiver is the position owner from the moment `use_external_gps` is
        called, so it reports its own state ("pi-nolink" — nothing heard yet)
        rather than naming a Pico receiver this board has no wiring for. See
        TestNoFixSourceReporting.
        """
        p = PicoSerial()
        p.use_external_gps()
        p._handle_tel(_tel_frame(lat="1.0", lon="2.0"))
        assert p.telemetry.lat == pytest_approx(1.0)
        assert p.telemetry.lon == pytest_approx(2.0)
        assert p.telemetry.gps_source == "pi-nolink"

    def test_fix_before_declaration_still_applies(self):
        """Tolerate wiring order rather than dropping position on the floor."""
        p = PicoSerial()
        p.set_external_position(37.5, -122.4)
        p._handle_tel(_tel_frame())
        assert p.telemetry.lat == pytest_approx(37.5)
        assert p.telemetry.gps_source == "pi"

    def test_apply_external_is_noop_without_source(self):
        p = PicoSerial()
        tel = Telemetry(lat=9.0, lon=9.0, health="111111")
        p._apply_external(tel)
        assert tel.lat == 9.0
        assert tel.health == "111111"


def _alert_frame(code="SENSOR_FAULT", detail="gps", severity="WARN"):
    payload = "ALERT,0,%s,%s,%s" % (severity, code, detail)
    return parse_frame(frame(payload).decode("ascii").strip())


class TestGpsAlertSuppression:
    def test_gps_fault_suppressed_with_external_source(self):
        p = PicoSerial()
        p.use_external_gps()
        p._handle_alert(_alert_frame())
        assert p.last_alert is None

    def test_gps_fault_surfaced_without_external_source(self):
        p = PicoSerial()
        p._handle_alert(_alert_frame())
        assert p.last_alert is not None
        assert p.last_alert.detail == "gps"

    def test_other_sensor_faults_still_surface(self):
        p = PicoSerial()
        p.use_external_gps()
        p._handle_alert(_alert_frame(detail="imu"))
        assert p.last_alert is not None
        assert p.last_alert.detail == "imu"

    def test_unrelated_alerts_still_surface(self):
        p = PicoSerial()
        p.use_external_gps()
        p._handle_alert(_alert_frame(code="BATT_LOW", detail="16.2,25"))
        assert p.last_alert is not None
        assert p.last_alert.code == "BATT_LOW"

    def test_callback_not_fired_for_suppressed_alert(self):
        p = PicoSerial()
        p.use_external_gps()
        seen = []
        p.on_alert(seen.append)
        p._handle_alert(_alert_frame())
        p._handle_alert(_alert_frame(detail="imu"))
        assert len(seen) == 1
        assert seen[0].detail == "imu"


class TestSatelliteView:
    """GSV parsing — the 'why is there no fix' fields."""

    def test_real_nolock_cycle_reports_two_audible_sats(self):
        """The exact bench state: 2 of 2 in view heard, best SNR 30."""
        p = NmeaParser()
        for line in NOLOCK_CYCLE:
            p.feed_line(line)
        assert p.sats_visible == 2
        assert p.sats_tracked == 2
        assert p.best_snr == 30

    def test_trailing_signal_id_is_not_read_as_a_satellite(self):
        """NMEA 4.10 appends signalId after the last group; it must not become a PRN.

        GSV_GP_2SAT ends ",30,1" — the 1 is signalId. Counting it would invent a
        third satellite with SNR 0, inflating sats_visible's companion count.
        """
        p = NmeaParser()
        p.feed_line(GSV_GP_2SAT)
        assert p.sats_tracked == 2
        assert sorted(p._gsv_snr["GP"]) == ["03", "04"]

    def test_empty_constellation_contributes_nothing(self):
        p = NmeaParser()
        for line in (GSV_GA_EMPTY, GSV_GB_EMPTY, GSV_GQ_EMPTY):
            p.feed_line(line)
        assert p.sats_visible == 0
        assert p.sats_tracked == 0
        assert p.best_snr == 0

    def test_counts_sum_across_talkers(self):
        """Each constellation runs its own GSV cycle; a flat total would be
        overwritten by whichever talker spoke last."""
        p = NmeaParser()
        p.feed_line(GSV)            # GPGSV, 8 in view
        p.feed_line(GSV_GA_EMPTY)   # GAGSV, 0 in view
        assert p.sats_visible == 8
        p.feed_line(_cksum("GAGSV,1,1,03,11,45,100,40,12,30,200,38,13,,,0,7"))
        assert p.sats_visible == 11
        assert p.best_snr == 40     # a Galileo bird now beats GP's 37

    def test_declared_count_is_right_from_the_first_message(self):
        """GSV's own count field is used, not the number of entries parsed, so a
        multi-message cycle doesn't ramp up as it arrives. GSV is msg 1 of 2 and
        carries 4 entries but declares 8."""
        p = NmeaParser()
        p.feed_line(GSV)
        assert p.sats_visible == 8
        assert p.sats_tracked == 4

    def test_blank_snr_is_in_view_but_not_tracked(self):
        """A satellite predicted from the almanac but not heard has no SNR — the
        gap between visible and tracked is the diagnostic signal."""
        p = NmeaParser()
        p.feed_line(_cksum("GPGSV,1,1,03,03,10,100,,04,20,200,,07,54,274,31,1"))
        assert p.sats_visible == 3
        assert p.sats_tracked == 1
        assert p.best_snr == 31

    def test_new_cycle_drops_satellites_that_left_view(self):
        p = NmeaParser()
        p.feed_line(_cksum("GPGSV,1,1,02,03,,,24,04,,,30,1"))
        assert p.sats_tracked == 2
        p.feed_line(_cksum("GPGSV,1,1,01,03,,,24,1"))
        assert p.sats_tracked == 1
        assert p.sats_visible == 1

    def test_multi_message_cycle_accumulates_then_replaces(self):
        p = NmeaParser()
        p.feed_line(_cksum("GPGSV,2,1,06,01,,,20,02,,,21,03,,,22,04,,,23,1"))
        p.feed_line(_cksum("GPGSV,2,2,06,05,,,24,06,,,25,1"))
        assert p.sats_tracked == 6
        assert p.best_snr == 25
        # A fresh msg 1 restarts the set rather than adding to it.
        p.feed_line(_cksum("GPGSV,2,1,02,01,,,20,1"))
        assert p.sats_tracked == 1

    def test_gsv_is_not_a_position_update(self):
        p = NmeaParser()
        assert p.feed_line(GSV_GP_2SAT) is None
        assert p.position_updates == 0
        assert p.sentences == 1

    def test_truncated_gsv_is_ignored_not_fatal(self):
        p = NmeaParser()
        assert p.feed_line(_cksum("GPGSV,1,1")) is None
        assert p.sats_visible == 0


class TestStatusCallback:
    def test_linked_is_false_until_a_sentence_arrives(self):
        g = NmeaGps()
        assert not g.linked
        g.parser.feed_line(GGA_NOLOCK)
        assert g.linked

    def test_linked_ignores_corrupt_sentences(self):
        """A port full of noise is not a talking receiver."""
        g = NmeaGps()
        g.parser.feed_line("$GNGGA,213321.00,,,,,0,00,99.99,,,,,,*00")
        assert not g.linked
        assert g.parser.bad_checksum == 1

    def test_stats_carry_the_satellite_view(self):
        g = NmeaGps()
        for line in NOLOCK_CYCLE:
            g.parser.feed_line(line)
        s = g.stats()
        assert s.sats_visible == 2
        assert s.sats_tracked == 2
        assert s.best_snr == 30
        assert s.linked
        assert not s.fix.has_fix


class TestNoFixSourceReporting:
    """`gps_source` must name the Pi receiver's state, never fall back to "pico".

    Before this, a receiver streaming perfectly but not locked reported "pico" —
    a receiver this board has no wiring for — which read as "the GPS is broken".
    """

    def test_streaming_but_unlocked_reports_pi_nofix(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_gps_status(sats_visible=2, sats_tracked=2,
                                  best_snr=30, linked=True)
        p._handle_tel(_tel_frame())
        t = p.telemetry
        assert t.gps_source == "pi-nofix"
        assert t.gps_sats_visible == 2
        assert t.gps_sats_tracked == 2
        assert t.gps_best_snr == 30
        assert t.fix_quality == 0

    def test_silent_receiver_reports_pi_nolink(self):
        p = PicoSerial()
        p.use_external_gps()
        p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pi-nolink"

    def test_nolink_needs_no_status_callback_to_be_reported(self):
        """The port may never open, so on_status may never fire — TEL alone has
        to be enough to report it."""
        p = PicoSerial()
        p.use_external_gps()
        for _ in range(3):
            p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pi-nolink"
        assert p.telemetry.gps_sats_visible == 0

    def test_health_bit0_cleared_while_unlocked(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_gps_status(sats_tracked=2, linked=True)
        p._handle_tel(_tel_frame(health="111110"))
        assert p.telemetry.health == "011110"

    def test_no_pi_gps_still_reports_pico(self):
        """The 'pico' rung must survive for a build that really is Pico-hosted."""
        p = PicoSerial()
        p.set_external_gps_status(sats_tracked=2, linked=True)
        p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pico"

    def test_first_fix_promotes_nofix_to_pi(self):
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_gps_status(sats_tracked=2, linked=True)
        p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pi-nofix"
        p.set_external_position(LAT, LON, fix_quality=1, sats=6)
        p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pi"
        assert p.telemetry.lat == pytest_approx(LAT)

    def test_satellite_view_survives_a_fix(self):
        """The sky fields stay live once locked — useful for watching quality."""
        p = PicoSerial()
        p.use_external_gps()
        p.set_external_position(LAT, LON, fix_quality=1, sats=6)
        p.set_external_gps_status(sats_visible=11, sats_tracked=9,
                                  best_snr=44, linked=True)
        p._handle_tel(_tel_frame())
        t = p.telemetry
        assert t.gps_source == "pi"
        assert t.gps_sats_visible == 11
        assert t.gps_best_snr == 44

    def test_losing_a_fix_goes_stale_not_nofix(self):
        """Deliberate asymmetry: `pi-nofix` means *never* locked. A receiver that
        locks then loses it keeps serving the last position as `pi-stale`, which
        is the pre-existing contract the nav stack relies on."""
        p = PicoSerial()
        p.use_external_gps(max_age_s=0.01)
        p.set_external_position(LAT, LON, fix_quality=1)
        p.set_external_gps_status(sats_tracked=0, linked=True)
        time.sleep(0.02)
        p._handle_tel(_tel_frame())
        assert p.telemetry.gps_source == "pi-stale"
        assert p.telemetry.lat == pytest_approx(LAT)


def pytest_approx(v, tol=1e-6):
    """Local approx so this module doesn't depend on pytest's namespace import."""
    from pytest import approx
    return approx(v, abs=tol)


def test_gpsfix_defaults_have_no_fix():
    assert not GpsFix().has_fix
