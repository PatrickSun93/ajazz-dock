"""
Ajazz AKP153E (VID 0x0300 PID 0x1010, protocol v1) HID driver.

Wire protocol — every output report is 512 bytes, zero-padded, prefixed with
report ID 0 (so 513 bytes are written). Command prefix is ASCII "CRT\\0\\0".

    Init / wake          CRT\\0\\0DIS, then CRT\\0\\0LIG\\0\\0\\0\\0 (two writes)
    Sleep                CRT\\0\\0HAN
    Brightness (0-100)   CRT\\0\\0LIG\\0\\0<pct>
    Image header         CRT\\0\\0BAT\\0\\0<size_hi><size_lo><keyId>   (size is BE u16)
    Image payload        raw JPEG bytes split into 512-byte chunks
    Batch commit         CRT\\0\\0STP   — send ONCE after a batch of images,
                                          NOT per image (mirajazz convention).
    Clear key            CRT\\0\\0CLE\\0\\0<tg0><tg1>   tg1=1..18 or 0xFF=all
    Firmware version     feature report 0x01 (read)

Images: JPEG (RGB), 95x95, pre-rotated 90 degrees.

Input report (key press): 512-byte read; bytes 0..8 == b"ACK\\0\\0OK\\0\\0",
byte 9 == key id (1..15, column-major). Press-only — no release event.
"""

from __future__ import annotations

import io
import os
import struct
import sys
from typing import Optional

import hid
from PIL import Image

DEBUG = os.environ.get("DOCK_DEBUG") == "1"


VID = 0x0300
PID = 0x1010

PACKET = 512                  # bytes per HID output report payload
KEYS = 15                     # 3 cols x 5 rows physical
LOGICAL_SLOTS = 18            # includes 3 logo/icon slots (16..18)

# Image dimensions and rotation can be overridden via env vars while we
# nail down what the AKP153E firmware actually expects. Defaults follow
# mirajazz for v1.
IMAGE_SIZE = (
    int(os.environ.get("DOCK_IMAGE_W", "95")),
    int(os.environ.get("DOCK_IMAGE_H", "95")),
)
IMAGE_ROTATE = int(os.environ.get("DOCK_IMAGE_ROTATE", "90"))  # 0/90/180/270

_CRT = b"CRT\x00\x00"
# mirajazz only checks the first 3 bytes ("ACK") of input frames. We saw the
# full prefix as `ACK\0\0OK\0\0<key>` in probe.py, but bytes 3..8 may vary
# after the device receives output commands, so we keep the loose check.
_INPUT_PREFIX = b"ACK"


def _pad(payload: bytes) -> bytes:
    if len(payload) > PACKET:
        raise ValueError(f"payload {len(payload)} > {PACKET}")
    return payload + b"\x00" * (PACKET - len(payload))


class DockDevice:
    def __init__(self, path: Optional[bytes] = None):
        self._dev = hid.device()
        if path is not None:
            self._dev.open_path(path)
        else:
            self._dev.open(VID, PID)
        self._dev.set_nonblocking(True)

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass

    def __enter__(self) -> "DockDevice":
        self.init()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- output ---------------------------------------------------------

    def _write(self, payload: bytes) -> None:
        # hidapi on Windows expects report ID byte prepended.
        self._dev.write(b"\x00" + _pad(payload))

    def _write_raw_chunk(self, chunk: bytes) -> None:
        self._dev.write(b"\x00" + _pad(chunk))

    def init(self) -> None:
        # Two-step wake per mirajazz: DIS, then LIG with all-zero brightness
        # frame (presumably acks the brightness channel). Actual brightness
        # gets set via set_brightness() afterwards if config supplies one.
        self._write(_CRT + b"DIS")
        self._write(_CRT + b"LIG\x00\x00\x00\x00")

    def sleep(self) -> None:
        self._write(_CRT + b"HAN")

    def set_brightness(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        self._write(_CRT + b"LIG\x00\x00" + bytes([pct]))

    def flush(self) -> None:
        """Commit pending image uploads. Send once after a batch, not per image."""
        self._write(_CRT + b"STP")

    def clear_key(self, key: int) -> None:
        # tg0=0x00, tg1=keyId or 0xFF for all
        self._write(_CRT + b"CLE\x00\x00" + bytes([0x00, key & 0xFF]))

    def clear_all(self) -> None:
        self.clear_key(0xFF)

    def set_image(self, key: int, image: "Image.Image | str") -> None:
        """Push an image to the LCD under `key` (1..15).

        `image` may be a PIL Image or a path. It will be resized to 95x95,
        rotated 90 degrees (the device displays as-received), and JPEG-encoded.
        Caller must invoke `flush()` once after a batch of `set_image` calls
        to make the new images visible.
        """
        if not 1 <= key <= LOGICAL_SLOTS:
            raise ValueError(f"key {key} out of range 1..{LOGICAL_SLOTS}")

        img = Image.open(image) if isinstance(image, str) else image
        img = img.convert("RGB").resize(IMAGE_SIZE, Image.LANCZOS)
        if IMAGE_ROTATE:
            img = img.rotate(IMAGE_ROTATE, expand=False)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        jpeg = buf.getvalue()

        # BAT header: CRT\0\0 BAT\0\0 <size BE u16> <keyId>. keyId on the wire
        # is 1-indexed; our `key` arg is already 1..15 from the config.
        header = _CRT + b"BAT\x00\x00" + struct.pack(">H", len(jpeg)) + bytes([key])
        self._write(header)

        for off in range(0, len(jpeg), PACKET):
            self._write_raw_chunk(jpeg[off:off + PACKET])

    # ---- input ----------------------------------------------------------

    def read_key(self, timeout_ms: int = 100) -> Optional[int]:
        """Return the 1..15 key id, or None on timeout / unknown frame."""
        data = self._dev.read(PACKET, timeout_ms=timeout_ms)
        if not data:
            return None
        buf = bytes(data)
        if len(buf) >= 10 and buf[:3] == _INPUT_PREFIX:
            key = buf[9]
            if 1 <= key <= LOGICAL_SLOTS:
                return key
        if DEBUG:
            head = " ".join(f"{b:02x}" for b in buf[:32])
            print(f"[raw-in {len(buf):>3}B] {head}", file=sys.stderr)
        return None
