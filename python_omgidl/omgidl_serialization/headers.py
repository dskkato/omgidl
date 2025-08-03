from __future__ import annotations

import struct
from typing import Tuple

EXTENDED_PID = 0x3F01
SENTINEL_PID = 0x3F02


def _padding(offset: int, byte_width: int) -> int:
    alignment = (offset - 4) % byte_width
    return 0 if alignment == 0 else byte_width - alignment


def read_delimiter_header(view: memoryview, offset: int, fmt_prefix: str) -> Tuple[int, int]:
    size = struct.unpack_from(fmt_prefix + "I", view, offset)[0]
    return size, offset + 4


def write_delimiter_header(buffer: bytearray, offset: int, fmt_prefix: str, size: int) -> int:
    struct.pack_into(fmt_prefix + "I", buffer, offset, size)
    return offset + 4


def read_member_header(view: memoryview, offset: int, fmt_prefix: str) -> Tuple[int | None, int, bool, int]:
    offset += _padding(offset, 4)
    id_header = struct.unpack_from(fmt_prefix + "H", view, offset)[0]
    pid = id_header & 0x3FFF
    if pid == SENTINEL_PID:
        return None, 0, True, offset + 4
    must_understand = (id_header & 0x4000) != 0
    offset += 2
    if pid == EXTENDED_PID:
        offset += 2  # skip size of next fields
        member_id = struct.unpack_from(fmt_prefix + "I", view, offset)[0]
        offset += 4
        obj_size = struct.unpack_from(fmt_prefix + "I", view, offset)[0]
        offset += 4
    else:
        member_id = pid
        obj_size = struct.unpack_from(fmt_prefix + "H", view, offset)[0]
        offset += 2
    return member_id, obj_size, must_understand, offset


def write_member_header(
    buffer: bytearray,
    offset: int,
    fmt_prefix: str,
    member_id: int,
    object_size: int,
    must_understand: bool = False,
) -> int:
    offset += _padding(offset, 4)
    header = (0x4000 if must_understand else 0) | (member_id & 0x3FFF)
    struct.pack_into(fmt_prefix + "H", buffer, offset, header)
    struct.pack_into(fmt_prefix + "H", buffer, offset + 2, object_size & 0xFFFF)
    return offset + 4


def write_sentinel_header(buffer: bytearray, offset: int, fmt_prefix: str) -> int:
    offset += _padding(offset, 4)
    struct.pack_into(fmt_prefix + "H", buffer, offset, SENTINEL_PID)
    struct.pack_into(fmt_prefix + "H", buffer, offset + 2, 0)
    return offset + 4


def read_sentinel_header(view: memoryview, offset: int, fmt_prefix: str) -> int:
    offset += _padding(offset, 4)
    header = struct.unpack_from(fmt_prefix + "H", view, offset)[0]
    pid = header & 0x3FFF
    if pid != SENTINEL_PID:
        raise ValueError("Expected sentinel header")
    return offset + 4
