#!/usr/bin/env python3
"""Talk to Sennheiser Momentum 4 headphones and print one JSON object.

The bar widget runs this once per action or refresh, so nothing stays
resident between clicks. Standard library only, so there is nothing to build.

    m4.py status                 print the headphone settings and audio output
    m4.py set <setting> <value>  change one setting, then print the new state

Settings: noise adaptive|custom|off, transparency 0-100, anti-wind
off|auto|max, auto-off never|15|30|60, and on|off for bass-boost, speech,
on-head, smart-pause, auto-answer, comfort-call, touch.

The headphones speak Qualcomm's GAIA protocol over a Bluetooth RFCOMM
channel. Command ids come from the reverse engineering in
DanSmith888/omarchy-momentum4 (MIT) and timmo001/omarchy-momentumctl
(Apache-2.0). Only ids known to be safe are ever sent: probing unknown ones
has made these headphones forget pairings and drop off the bus.

Headphone settings need the Bluetooth link. Over the USB cable alone only the
audio output is reported.
"""

import fcntl
import json
import os
import socket
import struct
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Self, TypedDict

MAGIC = b"\xff\x03"
VENDOR = 0x0495  # Sennheiser
TIMEOUT = 3.0
# GAIA isn't advertised cleanly over SDP, so try the channels it is usually
# on. The one that answered last time goes first.
CHANNELS = [15, 1, 2, 14, 12, 3, 4, 5, 6, 7, 8, 9, 10, 11]

BATTERY = 0x0603
GET_ANC, SET_ANC = 0x1A05, 0x1A04
# 0 is full noise cancelling, 100 full transparency.
GET_TRANSPARENCY, SET_TRANSPARENCY = 0x1A03, 0x1A02
# Six bytes of (id, value) pairs, written back whole.
GET_NOISE, SET_NOISE = 0x1A01, 0x1A00
NOISE_ANTI_WIND, NOISE_ADAPTIVE = 1, 5
ANTI_WIND = ["off", "max", "auto"]
# A "disabled" flag: 0 means the touch controls work.
GET_TOUCH, SET_TOUCH = 0x1607, 0x1606
# Index byte 0, then seconds as a big-endian u16, 0 for never.
GET_AUTO_OFF, SET_AUTO_OFF = 0x0601, 0x0600
FIRMWARE = 0x1201
# Big-endian u16: 1 graphic EQ, 2 Speech Clarity.
GET_SOUND_MODE, SET_SOUND_MODE = 0x0804, 0x0803
SWITCHES = {
    "bass-boost": (0x1009, 0x1008),
    "on-head": (0x0401, 0x0400),
    "smart-pause": (0x080D, 0x080C),
    "auto-answer": (0x080B, 0x080A),
    "comfort-call": (0x0815, 0x0814),
}

CODECS = {
    "sbc": "SBC",
    "sbc_xq": "SBC-XQ",
    "aac": "AAC",
    "aptx": "aptX",
    "aptx_hd": "aptX HD",
    "aptx_ll": "aptX LL",
    "ldac": "LDAC",
    "lc3": "LC3",
    "msbc": "mSBC",
    "cvsd": "CVSD",
}
# Codecs of the headset (call) profile: mono, 16 or 8 kHz.
CALL_CODECS = {"msbc", "cvsd", "lc3_swb"}

Noise = Literal["adaptive", "custom", "off"]


class M4Error(Exception):
    pass


class Rejected(M4Error):
    """The headphones answered with GAIA's error form."""


class Output(TypedDict):
    # bluetooth, usb (the Momentum 4 over the cable), or other (speakers).
    kind: str
    name: str
    codec: str | None
    call: bool
    rate: int | None
    format: str | None


class State(TypedDict, total=False):
    connected: bool
    output: Output
    battery: int
    noise: Noise
    transparency: int
    antiWind: str
    bassBoost: bool | None
    speech: bool | None
    onHead: bool
    smartPause: bool
    autoAnswer: bool
    comfortCall: bool
    touch: bool | None
    autoOff: int | None
    firmware: str | None


def main(argv: list[str]) -> int:
    try:
        out: Any = run(argv)
        code = 0
    except (M4Error, OSError) as e:
        out = {"error": str(e), "connected": False, "output": output()}
        code = 1
    print(json.dumps(out))
    return code


def run(argv: list[str]) -> State:
    match argv:
        case ["status"]:
            return status()
        case ["set", name, value]:
            with Session() as s:
                apply(s, name, value)
                return read(s)
    raise M4Error("usage: m4.py status | set <setting> <value>")


def status() -> State:
    if not address():
        return {"connected": False, "output": output()}
    with Session() as s:
        return read(s)


def read(s: "Session") -> State:
    noise = s.request(GET_NOISE)
    if len(noise) < 6:
        raise M4Error("short noise control reply")
    anc = s.byte(GET_ANC) != 0
    state: State = {
        "connected": True,
        "output": output(s.address),
        "battery": s.byte(BATTERY),
        "noise": "off"
        if not anc
        else "adaptive"
        if noise[NOISE_ADAPTIVE]
        else "custom",
        "transparency": s.byte(GET_TRANSPARENCY),
        "antiWind": ANTI_WIND[noise[NOISE_ANTI_WIND]]
        if noise[NOISE_ANTI_WIND] < 3
        else "unknown",
        "onHead": s.byte(SWITCHES["on-head"][0]) != 0,
        "smartPause": s.byte(SWITCHES["smart-pause"][0]) != 0,
        "autoAnswer": s.byte(SWITCHES["auto-answer"][0]) != 0,
        "comfortCall": s.byte(SWITCHES["comfort-call"][0]) != 0,
    }
    # Newer settings are missing on older firmware, so a rejection reports
    # them as unsupported instead of failing the whole status.
    state["bassBoost"] = s.optional(lambda: s.byte(SWITCHES["bass-boost"][0]) != 0)
    state["touch"] = s.optional(lambda: s.byte(GET_TOUCH) == 0)
    state["speech"] = s.optional(lambda: u16(s.request(GET_SOUND_MODE)) == 2)
    state["autoOff"] = s.optional(
        lambda: u16(s.request(GET_AUTO_OFF, b"\x00")[1:]) // 60
    )
    state["firmware"] = s.optional(
        lambda: ".".join(str(v) for v in struct.unpack(">3H", s.request(FIRMWARE)[:6]))
    )
    return state


def apply(s: "Session", name: str, value: str) -> None:
    match name, value:
        case "noise", "off":
            s.request(SET_ANC, b"\x00")
        case "noise", "adaptive" | "custom":
            s.request(SET_ANC, b"\x01")
            write_noise(s, NOISE_ADAPTIVE, 1 if value == "adaptive" else 0)
        case "anti-wind", mode if mode in ANTI_WIND:
            write_noise(s, NOISE_ANTI_WIND, ANTI_WIND.index(mode))
        case "transparency", level if level.isdigit() and int(level) <= 100:
            s.request(SET_TRANSPARENCY, bytes([int(level)]))
        case "speech", "on" | "off":
            s.request(SET_SOUND_MODE, struct.pack(">H", 2 if value == "on" else 1))
        case "touch", "on" | "off":
            s.request(SET_TOUCH, b"\x00" if value == "on" else b"\x01")
        case "auto-off", "never" | "15" | "30" | "60":
            seconds = 0 if value == "never" else int(value) * 60
            s.request(SET_AUTO_OFF, b"\x00" + struct.pack(">H", seconds))
        case switch, "on" | "off" if switch in SWITCHES:
            s.request(SWITCHES[switch][1], b"\x01" if value == "on" else b"\x00")
        case _:
            raise M4Error(f"unknown setting: {name} {value}")


def write_noise(s: "Session", field: int, value: int) -> None:
    """The noise table only takes whole writes, so change one field in place."""
    table = bytearray(s.request(GET_NOISE))
    if len(table) < 6:
        raise M4Error("short noise control reply")
    table[field] = value
    s.request(SET_NOISE, bytes(table))


class Session:
    """One RFCOMM connection to the headphones. Only one process can hold
    the GAIA channel, so the panel and a terminal take turns on a lock."""

    def __init__(self) -> None:
        mac = address()
        if not mac:
            raise M4Error("headphones not connected over Bluetooth")
        self.address = mac
        self.buffer = b""
        runtime = Path(
            os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/omarchy-momentum-{os.getuid()}"
        )
        runtime.mkdir(parents=True, exist_ok=True)
        self.lock = os.open(
            runtime / "omarchy-momentum.lock",
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC,
            0o600,
        )
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.cache = runtime / f"omarchy-momentum-channel-{mac.replace(':', '')}"
        self.sock = self.connect()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.sock.close()
        os.close(self.lock)

    def connect(self) -> socket.socket:
        try:
            cached = int(self.cache.read_text())
        except (OSError, ValueError):
            cached = 0
        for channel in (
            [cached, *(c for c in CHANNELS if c != cached)] if cached else CHANNELS
        ):
            sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            sock.settimeout(TIMEOUT)
            try:
                sock.connect((self.address, channel))
                self.sock = sock
                self.request(GET_ANC)  # a channel that isn't GAIA won't answer this
            except ConnectionRefusedError:
                sock.close()
                continue
            except (M4Error, OSError) as e:
                sock.close()
                # A timeout means the headphones are out of reach, so the
                # other channels would only add more waits.
                if isinstance(e, TimeoutError):
                    raise M4Error("headphones not responding") from e
                continue
            if channel != cached:
                self.cache.write_text(str(channel))
            return sock
        raise M4Error("no control channel answered")

    def request(self, command: int, payload: bytes = b"") -> bytes:
        """Send a command and return its reply's payload. Replies set bit 8
        of the command, errors also bit 7; anything else is a notification."""
        self.sock.sendall(
            MAGIC + struct.pack(">HHH", len(payload), VENDOR, command) + payload
        )
        while True:
            while len(self.buffer) >= 8:
                if self.buffer[:2] != MAGIC:
                    self.buffer = self.buffer[1:]
                    continue
                length, _, reply = struct.unpack(">HHH", self.buffer[2:8])
                if len(self.buffer) < 8 + length:
                    break
                body, self.buffer = (
                    self.buffer[8 : 8 + length],
                    self.buffer[8 + length :],
                )
                if reply == command | 0x0100:
                    return body
                if reply == command | 0x0180:
                    raise Rejected(f"headphones rejected command 0x{command:04x}")
            chunk = self.sock.recv(1024)
            if not chunk:
                raise M4Error("headphones closed the connection")
            self.buffer += chunk

    def byte(self, command: int) -> int:
        reply = self.request(command)
        if not reply:
            raise M4Error(f"empty reply to 0x{command:04x}")
        return reply[0]

    def optional[T](self, read: Callable[[], T]) -> T | None:
        try:
            return read()
        except (Rejected, IndexError, struct.error):
            return None


def u16(data: bytes) -> int:
    return struct.unpack(">H", data[:2])[0]


def address() -> str | None:
    """MAC of the connected Momentum 4, if any. Checked first so nothing
    tries the radio while the headphones are off or away."""
    try:
        out = subprocess.run(
            ["bluetoothctl", "devices", "Connected"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if (
            len(parts) == 3
            and parts[0] == "Device"
            and "MOMENTUM 4" in parts[2].upper()
        ):
            return parts[1]
    return None


def output(mac: str | None = None) -> Output:
    """Where the default output sends audio, and in what format. PipeWire
    picks the codec, not the headphones, so it comes from pactl."""
    none: Output = {
        "kind": "other",
        "name": "",
        "codec": None,
        "call": False,
        "rate": None,
        "format": None,
    }
    try:
        default = pa(["get-default-sink"]).strip()
        sinks = json.loads(pa(["--format=json", "list", "sinks"]))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return none
    sink = next((s for s in sinks if s.get("name") == default), None)
    if not sink:
        return none
    props: dict[str, Any] = sink.get("properties", {})
    spec = str(sink.get("sample_specification", "")).split()
    rate = next(
        (int(t[:-2]) for t in spec if t.endswith("Hz") and t[:-2].isdigit()), None
    )
    fmt = spec[0] if spec else None
    name = str(props.get("device.description") or sink.get("description") or default)
    codec = props.get("api.bluez5.codec")
    if codec is not None and (
        mac is None or props.get("api.bluez5.address", "").upper() == mac.upper()
    ):
        return {
            "kind": "bluetooth",
            "name": name,
            "codec": CODECS.get(codec, codec),
            "call": codec in CALL_CODECS,
            "rate": rate,
            "format": None,
        }
    if props.get("device.bus") == "usb" and "MOMENTUM" in default.upper():
        return {
            "kind": "usb",
            "name": name,
            "codec": None,
            "call": False,
            "rate": rate,
            "format": fmt,
        }
    return {
        "kind": "other",
        "name": name,
        "codec": None,
        "call": False,
        "rate": rate,
        "format": fmt,
    }


def pa(args: list[str]) -> str:
    return subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=5, check=True
    ).stdout


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
