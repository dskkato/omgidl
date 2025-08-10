from __future__ import annotations

import struct
import sys
from array import array
from typing import Any, Dict, List, Tuple, cast

from omgidl_parser.parse import Field, Module, Struct
from omgidl_parser.parse import Union as IDLUnion

from .constants import UNION_DISCRIMINATOR_PROPERTY_KEY
from .deserialization_info_cache import (
    DeserializationInfoCache,
    FieldDeserializationInfo,
    StructDeserializationInfo,
    UnionDeserializationInfo,
)
from .headers import read_delimiter_header, read_member_header
from .message_writer import (
    _LITTLE_ENDIAN_KINDS,
    PRIMITIVE_FORMATS,
    PRIMITIVE_SIZES,
    EncapsulationKind,
    _find_struct,
    _padding,
    _primitive_size,
    _union_case_field,
)


class MessageReader:
    """Deserialize CDR-encoded bytes into Python dictionaries.

    This is a minimal Python port of the TypeScript MessageReader. It supports
    primitive fields, fixed-length arrays, and variable-length sequences as
    produced by the simplified ``parse_idl`` parser.
    """

    def __init__(
        self, root_definition_name: str, definitions: List[Struct | Module | IDLUnion]
    ) -> None:
        root = _find_struct(
            cast(List[Struct | Module], definitions), root_definition_name
        )
        if root is None:
            raise ValueError(
                f'Root definition name "{root_definition_name}" not found '
                "in schema definitions."
            )
        self.cache = DeserializationInfoCache(definitions)
        # ``_find_struct`` guarantees that ``root`` is a ``Struct`` definition,
        # so the returned complex deserialization info will always be for a
        # struct.  Casting here narrows the type for ``_read_struct`` calls.
        self.root_info: StructDeserializationInfo = cast(
            StructDeserializationInfo, self.cache.get_complex_deser_info(root)
        )
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
        msg, _ = self._read_struct(self.root_info, view, offset)
        return msg

    # internal helpers ------------------------------------------------------
    def _read_struct(
        self, info: StructDeserializationInfo, view: memoryview, offset: int
    ) -> Tuple[Dict[str, Any], int]:
        msg: Dict[str, Any] = self.cache.get_complex_default(info)
        new_offset = offset
        end = None
        if info.uses_delimiter_header:
            new_offset += _padding(new_offset, 4)
            length, new_offset = read_delimiter_header(
                view, new_offset, self._fmt_prefix
            )
            end = new_offset + length
        if info.uses_member_header:
            while True:
                field_id, size, new_offset = read_member_header(
                    view, new_offset, self._fmt_prefix
                )
                if field_id == 0:
                    break
                field = next((f for f in info.fields if f.id == field_id), None)
                if field is None:
                    new_offset += size
                    continue
                value, new_offset = self._read_field(field, view, new_offset)
                msg[field.name] = value
            if end is not None:
                new_offset = end
            return msg, new_offset
        for field in info.fields:
            value, new_offset = self._read_field(field, view, new_offset)
            msg[field.name] = value
        if end is not None and new_offset < end:
            new_offset = end
        return msg, new_offset

    def _read_field(
        self, field: FieldDeserializationInfo, view: memoryview, offset: int
    ) -> Tuple[Any, int]:
        t = field.type
        if field.is_array:
            lengths = field.array_lengths or []
            return self._read_array(field, view, offset, lengths)
        if field.is_sequence:
            offset += _padding(offset, 4)
            length = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
            offset += 4
            if t in ("string", "wstring"):
                seq: List[str] = []
                for _ in range(length):
                    offset += _padding(offset, 4)
                    slen = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                    offset += 4
                    term = 1 if t == "string" else 2
                    data = bytes(view[offset : offset + slen - term])
                    offset += slen
                    s = data.decode("utf-8" if t == "string" else "utf-16-le")
                    if (
                        field.string_upper_bound is not None
                        and len(s) > field.string_upper_bound
                    ):
                        raise ValueError(
                            f"Field '{field.name}' string length {len(s)} exceeds "
                            f"bound {field.string_upper_bound}"
                        )
                    seq.append(s)
                return seq, offset
            if t in PRIMITIVE_SIZES:
                size = _primitive_size(t)
                typecode = PRIMITIVE_FORMATS[t]
                offset += _padding(offset, size)
                byte_length = size * length
                data = view[offset : offset + byte_length]
                arr = array(typecode)
                arr.frombytes(data.tobytes())
                offset += byte_length
                if (self._fmt_prefix == "<" and sys.byteorder == "big") or (
                    self._fmt_prefix == ">" and sys.byteorder == "little"
                ):
                    arr.byteswap()
                return arr, offset
            if field.type_info is None:
                raise ValueError(f"Unrecognized struct or union type {t}")
            seq_arr: List[Any] = []
            for _ in range(length):
                if isinstance(field.type_info, StructDeserializationInfo):
                    msg, offset = self._read_struct(field.type_info, view, offset)
                else:
                    msg, offset = self._read_union(field.type_info, view, offset)
                seq_arr.append(msg)
            return seq_arr, offset

        if t in ("string", "wstring"):
            offset += _padding(offset, 4)
            length = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
            offset += 4
            term = 1 if t == "string" else 2
            data = bytes(view[offset : offset + length - term])
            offset += length
            s = data.decode("utf-8" if t == "string" else "utf-16-le")
            if (
                field.string_upper_bound is not None
                and len(s) > field.string_upper_bound
            ):
                raise ValueError(
                    f"Field '{field.name}' string length {len(s)} exceeds "
                    f"bound {field.string_upper_bound}"
                )
            return s, offset
        if t in PRIMITIVE_SIZES:
            size = _primitive_size(t)
            fmt = self._fmt_prefix + PRIMITIVE_FORMATS[t]
            offset += _padding(offset, size)
            val = struct.unpack_from(fmt, view, offset)[0]
            offset += size
            if t == "bool":
                val = bool(val)
            return val, offset

        if field.type_info is None:
            raise ValueError(f"Unrecognized struct or union type {t}")
        if isinstance(field.type_info, StructDeserializationInfo):
            return self._read_struct(field.type_info, view, offset)
        return self._read_union(field.type_info, view, offset)

    def _read_array(
        self,
        field: FieldDeserializationInfo,
        view: memoryview,
        offset: int,
        lengths: List[int],
    ) -> Tuple[Any, int]:
        t = field.type
        length = lengths[0]
        if len(lengths) > 1:
            nested: List[Any] = []
            for _ in range(length):
                sub, offset = self._read_array(field, view, offset, lengths[1:])
                nested.append(sub)
            return nested, offset

        if t in ("string", "wstring"):
            text_arr: List[str] = []
            for _ in range(length):
                offset += _padding(offset, 4)
                slen = struct.unpack_from(self._fmt_prefix + "I", view, offset)[0]
                offset += 4
                term = 1 if t == "string" else 2
                data = bytes(view[offset : offset + slen - term])
                offset += slen
                s = data.decode("utf-8" if t == "string" else "utf-16-le")
                if (
                    field.string_upper_bound is not None
                    and len(s) > field.string_upper_bound
                ):
                    raise ValueError(
                        f"Field '{field.name}' string length {len(s)} exceeds "
                        f"bound {field.string_upper_bound}"
                    )
                text_arr.append(s)
            return text_arr, offset

        if t in PRIMITIVE_SIZES:
            size = _primitive_size(t)
            typecode = PRIMITIVE_FORMATS[t]
            offset += _padding(offset, size)
            byte_length = size * length
            data = view[offset : offset + byte_length]
            prim_arr = array(typecode)
            prim_arr.frombytes(data.tobytes())
            offset += byte_length
            if (self._fmt_prefix == "<" and sys.byteorder == "big") or (
                self._fmt_prefix == ">" and sys.byteorder == "little"
            ):
                prim_arr.byteswap()
            return prim_arr, offset

        if field.type_info is None:
            raise ValueError(f"Unrecognized struct or union type {t}")
        items: List[Any] = []
        for _ in range(length):
            if isinstance(field.type_info, StructDeserializationInfo):
                msg, offset = self._read_struct(field.type_info, view, offset)
            else:
                msg, offset = self._read_union(field.type_info, view, offset)
            items.append(msg)
        return items, offset

    def _read_union(
        self, info: UnionDeserializationInfo, view: memoryview, offset: int
    ) -> Tuple[Dict[str, Any], int]:
        new_offset = offset
        end = None
        if info.uses_delimiter_header:
            new_offset += _padding(new_offset, 4)
            length, new_offset = read_delimiter_header(
                view, new_offset, self._fmt_prefix
            )
            end = new_offset + length
        if info.uses_member_header:
            msg: Dict[str, Any] = {}
            while True:
                field_id, size, new_offset = read_member_header(
                    view, new_offset, self._fmt_prefix
                )
                if field_id == 0:
                    break
                if field_id == 1:
                    disc_field = Field(
                        name=UNION_DISCRIMINATOR_PROPERTY_KEY,
                        type=info.definition.switch_type,
                    )
                    disc_info = self.cache.build_field_info(disc_field, 1)
                    disc, new_offset = self._read_field(disc_info, view, new_offset)
                    msg[UNION_DISCRIMINATOR_PROPERTY_KEY] = disc
                else:
                    disc = msg.get(UNION_DISCRIMINATOR_PROPERTY_KEY)
                    if disc is None:
                        new_offset += size
                        continue
                    case_field = _union_case_field(info.definition, disc)
                    if case_field is None:
                        new_offset += size
                        continue
                    case_info = self.cache.build_field_info(case_field, field_id)
                    value, new_offset = self._read_field(case_info, view, new_offset)
                    msg[case_field.name] = value
            if end is not None:
                new_offset = end
            return msg, new_offset
        disc_field = Field(
            name=UNION_DISCRIMINATOR_PROPERTY_KEY, type=info.definition.switch_type
        )
        disc_info = self.cache.build_field_info(disc_field)
        disc, new_offset = self._read_field(disc_info, view, new_offset)
        msg = {UNION_DISCRIMINATOR_PROPERTY_KEY: disc}
        case_field = _union_case_field(info.definition, disc)
        if case_field is None:
            if end is not None:
                new_offset = end
            return msg, new_offset
        case_info = self.cache.build_field_info(case_field)
        value, new_offset = self._read_field(case_info, view, new_offset)
        msg[case_field.name] = value
        if end is not None and new_offset < end:
            new_offset = end
        return msg, new_offset
