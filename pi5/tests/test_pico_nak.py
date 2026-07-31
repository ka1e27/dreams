"""Tests for command refusals (NAK) and the mirrored Pico ESTOP latch.

Both exist because of a live failure. The navigator logged
"SET_THR failed (manual): Command SET_THR NAK'd: SET_THR" at 5 Hz — reading
fields[0] of `NAK,<seq>,<command>,<reason>`, which is the echoed command, so the
one useful field (ESTOP / RC_ACTIVE / RANGE / PARSE) never reached the operator.
And because the firmware's estop is *latched*, a Pico that estopped minutes ago
keeps refusing every throttle command with nothing on the Pi saying why.
"""
from __future__ import annotations

import asyncio

import pytest

from pi5.comms.pico_serial import PicoNak, PicoSerial
from pi5.comms.protocol import checksum, parse_frame


def _frame(payload: str) -> str:
    return "$%s*%d" % (payload, checksum(payload))


class _LoopbackPico(PicoSerial):
    """PicoSerial with the wire replaced by a canned reply.

    `reply` is called with the sequence number of the command just sent and
    returns a payload string, which is parsed and dispatched exactly as the read
    loop would — so the ACK/NAK path under test is the real one.
    """

    def __init__(self, reply, **kwargs) -> None:
        super().__init__(command_timeout=0.2, max_retries=1, **kwargs)
        self._reply = reply
        self.sent: list[str] = []

    async def _send_raw(self, data: bytes) -> None:
        text = data.decode().strip()
        self.sent.append(text)
        # $CMD[,arg...]*<cs> — drop the checksum before reading the seq, or a
        # no-arg command like $RESUME,1*4 leaves it glued to the seq field.
        seq = int(text.lstrip("$").split("*")[0].split(",")[1])
        payload = self._reply(seq)
        if payload is not None:
            self._dispatch(parse_frame(_frame(payload)))


def _nak_with(reason: str):
    return lambda seq: "NAK,%d,SET_THR,%s" % (seq, reason)


class TestNakReason:
    """The reason is fields[1] — fields[0] echoes the command."""

    def test_estop_reason_is_reported_not_the_command_name(self):
        pico = _LoopbackPico(_nak_with("ESTOP"))
        with pytest.raises(PicoNak) as exc:
            asyncio.run(pico.set_throttle(30, 30))
        assert exc.value.reason == "ESTOP"
        assert exc.value.command == "SET_THR"
        assert "SET_THR NAK'd: ESTOP" in str(exc.value)

    def test_rc_active_reason(self):
        pico = _LoopbackPico(_nak_with("RC_ACTIVE"))
        with pytest.raises(PicoNak) as exc:
            asyncio.run(pico.set_throttle(30, 30))
        assert exc.value.reason == "RC_ACTIVE"

    def test_nak_is_a_runtime_error(self):
        """Existing `except RuntimeError` callers must keep catching it."""
        pico = _LoopbackPico(_nak_with("RANGE"))
        with pytest.raises(RuntimeError):
            asyncio.run(pico.set_throttle(30, 30))

    def test_short_nak_falls_back_to_the_only_field(self):
        pico = _LoopbackPico(lambda seq: "NAK,%d,PARSE" % seq)
        with pytest.raises(PicoNak) as exc:
            asyncio.run(pico.set_throttle(30, 30))
        assert exc.value.reason == "PARSE"

    def test_timeout_still_raises_timeout_not_nak(self):
        pico = _LoopbackPico(lambda seq: None)
        with pytest.raises(TimeoutError):
            asyncio.run(pico.set_throttle(30, 30))


class TestEstopLatch:
    """`estopped` mirrors the firmware's sticky motor_control.estop()."""

    def test_starts_clear(self):
        assert _LoopbackPico(_nak_with("ESTOP")).estopped is False

    def test_set_by_an_estop_nak(self):
        pico = _LoopbackPico(_nak_with("ESTOP"))
        with pytest.raises(PicoNak):
            asyncio.run(pico.set_throttle(30, 30))
        assert pico.estopped is True

    def test_not_set_by_an_unrelated_nak(self):
        pico = _LoopbackPico(_nak_with("RANGE"))
        with pytest.raises(PicoNak):
            asyncio.run(pico.set_throttle(30, 30))
        assert pico.estopped is False

    @pytest.mark.parametrize("code", ["ESTOP_AUTO", "HB_LOST", "SBUS_LOST"])
    def test_set_by_estop_class_alerts(self, code):
        pico = _LoopbackPico(lambda seq: None)
        pico._handle_alert(parse_frame(_frame("ALERT,0,CRIT,%s" % code)))
        assert pico.estopped is True

    def test_not_set_by_an_ordinary_alert(self):
        pico = _LoopbackPico(lambda seq: None)
        pico._handle_alert(parse_frame(_frame("ALERT,0,WARN,SENSOR_FAULT,imu")))
        assert pico.estopped is False

    def test_estop_command_latches_before_the_ack(self):
        """If the ACK is the thing that gets lost, the boat is still stopped."""
        pico = _LoopbackPico(lambda seq: None)
        with pytest.raises(TimeoutError):
            asyncio.run(pico.emergency_stop())
        assert pico.estopped is True

    def test_resume_clears_it_on_ack(self):
        pico = _LoopbackPico(lambda seq: "ACK,%d,RESUME" % seq)
        pico.estopped = True
        asyncio.run(pico.resume())
        assert pico.estopped is False

    def test_failed_resume_does_not_clear_it(self):
        pico = _LoopbackPico(lambda seq: None)
        pico.estopped = True
        with pytest.raises(TimeoutError):
            asyncio.run(pico.resume())
        assert pico.estopped is True


class _SilentLink:
    """A reader whose readline() never returns and never raises.

    This is what a re-enumerated USB CDC device leaves behind: the fd is still
    open, the device is gone, and the read just hangs. Nothing in the OS tells
    the process, so only a timeout can notice.
    """

    def __init__(self) -> None:
        self.reads = 0

    async def readline(self) -> bytes:
        self.reads += 1
        await asyncio.Event().wait()      # never completes
        return b""                        # unreachable


class TestSilentLinkSelfHeals:
    """A wedged link must be detected and reopened, not waited on forever."""

    def test_silence_forces_a_reconnect(self):
        pico = PicoSerial(silence_timeout=0.05)
        opens = []

        async def fake_open():
            opens.append(1)
            pico._reader = _SilentLink()
            pico._connected = True

        async def fake_close():
            pico._reader = None
            pico._connected = False

        pico._open_streams = fake_open
        pico._close_streams = fake_close

        async def run():
            task = asyncio.ensure_future(pico._read_loop())
            # Detection is fast (silence_timeout) but reopening waits out the
            # reconnect backoff, which starts at 0.5 s — so allow for both.
            await asyncio.sleep(1.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
        # Without the timeout this parks on the first readline forever: one open,
        # and no amount of waiting recovers it.
        assert len(opens) > 1, "wedged link never reconnected"
