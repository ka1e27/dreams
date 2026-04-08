"""Serial protocol primitives — frame encoding, checksum, parsing.

Shared by pico_serial.py and tests. Implements the frame format
defined in docs/serial-protocol.md.
"""
from __future__ import annotations

from dataclasses import dataclass


def checksum(payload: str) -> int:
    """XOR checksum over all characters in payload."""
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    return cs


def frame(payload: str) -> bytes:
    """Wrap a payload string in the wire frame: $payload*cs\\n"""
    cs = checksum(payload)
    return ("$%s*%d\n" % (payload, cs)).encode("ascii")


@dataclass
class ParsedFrame:
    """A validated, parsed message from the Boat Pico."""
    msg_type: str
    seq: int
    fields: list[str]
    raw: str


def parse_frame(line: str) -> ParsedFrame | None:
    """Parse a single frame line (already stripped of newline).

    Returns ParsedFrame on success, None if invalid.
    """
    line = line.strip()
    if not line or line[0] != "$":
        return None
    if "*" not in line:
        return None
    body = line[1:]  # strip '$'
    payload, cs_str = body.rsplit("*", 1)
    try:
        if checksum(payload) != int(cs_str):
            return None
    except ValueError:
        return None
    parts = payload.split(",")
    if len(parts) < 2:
        return None
    msg_type = parts[0]
    try:
        seq = int(parts[1])
    except ValueError:
        return None
    return ParsedFrame(
        msg_type=msg_type,
        seq=seq,
        fields=parts[2:],
        raw=payload,
    )


def build_command(msg_type: str, seq: int, *args: str | int | float) -> bytes:
    """Build a framed command ready to send over serial.

    Example: build_command("SET_THR", 12, 40, 40)
      → b"$SET_THR,12,40,40*71\\n"
    """
    parts = [msg_type, str(seq)]
    for a in args:
        if isinstance(a, float):
            parts.append("%.6f" % a if abs(a) < 1 else "%.1f" % a)
        else:
            parts.append(str(a))
    payload = ",".join(parts)
    return frame(payload)
