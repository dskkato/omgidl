from __future__ import annotations

import struct
from array import array
from typing import Any, Dict, List, Tuple

from omgidl_parser.parse import Struct, Field, Module, Union as IDLUnion

from .message_writer import (
    PRIMITIVE_FORMATS,
    PRIMITIVE_SIZES,
    EncapsulationKind,
    _LITTLE_ENDIAN_KINDS,
    _find_struct,
    _find_union,
    _union_case_field,
    _padding,
    _primitive_size,
)


class MessageReader:
    """Deserialize CDR-encoded bytes into Python dictionaries.

    This is a minimal Python port of the TypeScript MessageReader. It supports
    primitive fields, fixed-length arrays, and variable-length sequences as
    produced by the simplified ``parse_idl`` parser.
    """

    def __init__(self, root_definition_name: str, definitions: List[Struct | Module | IDLUnion]) -> None:
        root = _find_struct(definitions, root_definition_name)
        if root is None:
            raise ValueError(
                f'Root definition name "{root_definition_name}" not found in schema definitions.'
            )
        self.root = root
        self.definitions = definitions
        self._fmt_prefix = "<"
        self.encapsulation_kind = EncapsulationKind.CDR_LE

    # public API -------------------------------------------------------------
    def read_message(self, buffer: bytes | bytearray | memoryview) -> Dict[str, Any]:
        view = buffer if isinstance(buffer, memoryview) else memoryview(buffer)
        kind = EncapsulationKind(view[1])
        self.encapsulation_kind = kind
        little = kind in _LITTLE_ENDIAN_KINDS
        self._fmt_prefix = "<" if little else ">"
        offset = 4
        msg, _ = self._read(self.root.fields, view, offset)
        return msg

    # internal helpers ------------------------------------------------------
    def _read(self, definition: List[Field], view: memoryview, offset: int) -> Tuple[Dict[str, Any], int]:
        msg: Dict[str, Any] = {}
        new_offset = offset
        for field in definition:
            value, new_offset = self._read_field(field, view, new_offset)
            msg[field.name] = value
        return msg, new_offset

    def _read_field(self, field: Field, view: memoryview, offset: int) -> Tuple[Any, int]:
        t = field.type
        if field.array_lengths:
            return self._read_array(field, view, offset, field.array_lengths)
        else:
            if field.is_sequence:
                # Variable-length sequence
                offset += _padding(offset, 4)
                length = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                offset += 4
                if t in ("string", "wstring"):
                    arr: List[Any] = []
                    for _ in range(length):
                        offset += _padding(offset, 4)
                        slen = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                        offset += 4
                        term = 1 if t == "string" else 2
                        data = bytes(view[offset : offset + slen - term])
                        offset += slen
                        s = data.decode("utf-8" if t == "string" else "utf-16-le")
                        if field.string_upper_bound is not None and len(s) > field.string_upper_bound:
                            raise ValueError(
                                f"Field '{field.name}' string length {len(s)} exceeds bound {field.string_upper_bound}"
                            )
                        arr.append(s)
                elif t in PRIMITIVE_SIZES:
                    size = _primitive_size(t)
                    fmt = self._fmt_prefix + PRIMITIVE_FORMATS[t]
                    offset += _padding(offset, size)
                    arr = array(PRIMITIVE_FORMATS[t])
                    for _ in range(length):
                        val = struct.unpack_from(fmt, view, offset)[0]
                        offset += size
                        if t == "bool":
                            val = bool(val)
                        arr.append(val)
                else:
                    arr: List[Any] = []
                    struct_def = _find_struct(self.definitions, t)
                    if struct_def is not None:
                        for _ in range(length):
                            msg, offset = self._read(struct_def.fields, view, offset)
                            arr.append(msg)
                    else:
                        union_def = _find_union(self.definitions, t)
                        if union_def is None:
                            raise ValueError(f"Unrecognized struct or union type {t}")
                        for _ in range(length):
                            msg, offset = self._read_union(union_def, view, offset)
                            arr.append(msg)
                return arr, offset
            else:
                if t in ("string", "wstring"):
                    offset += _padding(offset, 4)
                    length = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                    offset += 4
                    term = 1 if t == "string" else 2
                    data = bytes(view[offset : offset + length - term])
                    offset += length
                    s = data.decode("utf-8" if t == "string" else "utf-16-le")
                    if field.string_upper_bound is not None and len(s) > field.string_upper_bound:
                        raise ValueError(
                            f"Field '{field.name}' string length {len(s)} exceeds bound {field.string_upper_bound}"
                        )
                    return s, offset
                elif t in PRIMITIVE_SIZES:
                    size = _primitive_size(t)
                    fmt = self._fmt_prefix + PRIMITIVE_FORMATS[t]
                    offset += _padding(offset, size)
                    val = struct.unpack_from(fmt, view, offset)[0]
                    offset += size
                    if t == "bool":
                        val = bool(val)
                    return val, offset
                else:
                    struct_def = _find_struct(self.definitions, t)
                    if struct_def is not None:
                        msg, offset = self._read(struct_def.fields, view, offset)
                        return msg, offset
                    else:
                        union_def = _find_union(self.definitions, t)
                        if union_def is None:
                            raise ValueError(f"Unrecognized struct or union type {t}")
                        msg, offset = self._read_union(union_def, view, offset)
                        return msg, offset

    def _read_array(
        self, field: Field, view: memoryview, offset: int, lengths: List[int]
    ) -> Tuple[Any, int]:
        t = field.type
        length = lengths[0]
        if len(lengths) > 1:
            arr: List[Any] = []
            for _ in range(length):
                sub, offset = self._read_array(field, view, offset, lengths[1:])
                arr.append(sub)
            return arr, offset
        if t in ("string", "wstring"):
            arr: List[str] = []
            for _ in range(length):
                offset += _padding(offset, 4)
                slen = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                offset += 4
                term = 1 if t == "string" else 2
                data = bytes(view[offset : offset + slen - term])
                offset += slen
                s = data.decode("utf-8" if t == "string" else "utf-16-le")
                if field.string_upper_bound is not None and len(s) > field.string_upper_bound:
                    raise ValueError(
                        f"Field '{field.name}' string length {len(s)} exceeds bound {field.string_upper_bound}"
                    )
                arr.append(s)
            return arr, offset
        elif t in PRIMITIVE_SIZES:
            size = _primitive_size(t)
            fmt = self._fmt_prefix + PRIMITIVE_FORMATS[t]
            arr = array(PRIMITIVE_FORMATS[t])
            offset += _padding(offset, size)
            for _ in range(length):
                val = struct.unpack_from(fmt, view, offset)[0]
                offset += size
                if t == "bool":
                    val = bool(val)
                arr.append(val)
            return arr, offset
        else:
            struct_def = _find_struct(self.definitions, t)
            arr: List[Any] = []
            if struct_def is not None:
                for _ in range(length):
                    msg, offset = self._read(struct_def.fields, view, offset)
                    arr.append(msg)
            else:
                union_def = _find_union(self.definitions, t)
                if union_def is None:
                    raise ValueError(f"Unrecognized struct or union type {t}")
                for _ in range(length):
                    msg, offset = self._read_union(union_def, view, offset)
                    arr.append(msg)
            return arr, offset

    def _read_union(self, union_def: IDLUnion, view: memoryview, offset: int) -> Tuple[Dict[str, Any], int]:
        disc_field = Field(name="_d", type=union_def.switch_type)
        disc, offset = self._read_field(disc_field, view, offset)
        msg: Dict[str, Any] = {"_d": disc}
        case_field = _union_case_field(union_def, disc)
        if case_field is None:
            return msg, offset
        value, offset = self._read_field(case_field, view, offset)
        msg[case_field.name] = value
        return msg, offset
