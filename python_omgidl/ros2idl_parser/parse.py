from __future__ import annotations

import re
from typing import List, Optional, TypeAlias

from foxglove_message_definition import MessageDefinition, MessageDefinitionField
from omgidl_parser.parse import Constant as IDLConstant
from omgidl_parser.parse import Enum as IDLEnum
from omgidl_parser.parse import Field as IDLField
from omgidl_parser.parse import Module as IDLModule
from omgidl_parser.parse import Struct as IDLStruct
from omgidl_parser.parse import Typedef as IDLTypedef
from omgidl_parser.parse import Union as IDLUnion
from omgidl_parser.parse import parse_idl
from omgidl_parser.process import build_map

IDLDefinition: TypeAlias = (
    IDLStruct | IDLModule | IDLConstant | IDLEnum | IDLUnion | IDLTypedef
)
IDLMap: TypeAlias = dict[str, IDLDefinition]

UNION_DISCRIMINATOR_PROPERTY_KEY = "$discriminator"

ROS2IDL_HEADER = re.compile(r"={80}\nIDL: [a-zA-Z][\w]*(?:\/[a-zA-Z][\w]*)*")


def parse_ros2idl(message_definition: str) -> List[MessageDefinition]:
    """Parse ros2idl schema into message definitions."""
    idl_conformed = ROS2IDL_HEADER.sub("", message_definition)
    parsed = parse_idl(idl_conformed)
    typedefs = _collect_typedefs(parsed, [])
    idl_map = build_map(parsed)
    message_defs: List[MessageDefinition] = []
    for definition in parsed:
        message_defs.extend(_process_definition(definition, [], typedefs, idl_map))

    for msg in message_defs:
        if msg.name is not None:
            msg.name = _normalize_name(msg.name)
        for field in msg.definitions:
            field.type = _normalize_name(field.type)
            if field.enumType:
                field.enumType = _normalize_name(field.enumType)

        if msg.name in (
            "builtin_interfaces/msg/Time",
            "builtin_interfaces/msg/Duration",
        ):
            for field in msg.definitions:
                if field.name == "nanosec":
                    field.name = "nsec"

    return message_defs


def _process_definition(
    defn: IDLDefinition,
    scope: List[str],
    typedefs: dict[str, IDLTypedef],
    idl_map: IDLMap,
) -> List[MessageDefinition]:
    results: List[MessageDefinition] = []
    if isinstance(defn, IDLStruct):
        fields = [_convert_field(f, typedefs, idl_map, scope) for f in defn.fields]
        results.append(
            MessageDefinition(name="/".join([*scope, defn.name]), definitions=fields)
        )
    elif isinstance(defn, IDLUnion):
        disc_field = _convert_field(
            IDLField(name=UNION_DISCRIMINATOR_PROPERTY_KEY, type=defn.switch_type),
            typedefs,
            idl_map,
            scope,
        )
        case_fields = [
            _convert_field(c.field, typedefs, idl_map, scope) for c in defn.cases
        ]
        default_field = (
            [_convert_field(defn.default, typedefs, idl_map, scope)]
            if defn.default is not None
            else []
        )
        fields = [disc_field, *case_fields, *default_field]
        results.append(
            MessageDefinition(name="/".join([*scope, defn.name]), definitions=fields)
        )
    elif isinstance(defn, IDLModule):
        module_scope = [*scope, defn.name]
        const_fields = [
            _convert_constant(c, typedefs, module_scope, idl_map)
            for c in defn.definitions
            if isinstance(c, IDLConstant)
        ]
        if const_fields:
            results.append(
                MessageDefinition(name="/".join(module_scope), definitions=const_fields)
            )
        for sub in defn.definitions:
            if isinstance(sub, (IDLModule, IDLStruct, IDLUnion, IDLEnum)):
                results.extend(
                    _process_definition(sub, module_scope, typedefs, idl_map)
                )
    elif isinstance(defn, IDLEnum):
        enum_scope = [*scope, defn.name]
        fields = [
            _convert_constant(e, typedefs, enum_scope, idl_map)
            for e in defn.enumerators
        ]
        results.append(MessageDefinition(name="/".join(enum_scope), definitions=fields))
    elif isinstance(defn, IDLConstant):
        results.append(
            MessageDefinition(
                name="/".join(scope),
                definitions=[_convert_constant(defn, typedefs, scope, idl_map)],
            )
        )
    # IDLTypedef does not directly produce MessageDefinitions here
    return results


def _convert_field(
    field: IDLField,
    typedefs: dict[str, IDLTypedef],
    idl_map: IDLMap,
    scope: List[str],
) -> MessageDefinitionField:
    current_type, _ = _resolve_scoped_type(field.type, scope, idl_map)
    array_lengths = list(field.array_lengths)
    is_sequence = field.is_sequence
    seq_bound = field.sequence_bound
    visited: set[str] = set()
    while current_type in typedefs and current_type not in visited:
        visited.add(current_type)
        td = typedefs[current_type]
        next_type, _ = _resolve_scoped_type(td.type, scope, idl_map)
        current_type = next_type
        if td.array_lengths:
            array_lengths.extend(td.array_lengths)
        if td.is_sequence:
            is_sequence = True
            if td.sequence_bound is not None:
                seq_bound = td.sequence_bound
    if len(array_lengths) > 1:
        raise ValueError(
            "Multi-dimensional arrays are not supported in MessageDefinition type"
        )
    enum_type: Optional[str] = None
    is_complex = False
    final_type, ref = _resolve_scoped_type(current_type, scope, idl_map)
    if isinstance(ref, IDLEnum):
        enum_type = _normalize_name(final_type)
        final_type = "uint32"
    elif isinstance(ref, (IDLStruct, IDLUnion)):
        is_complex = True
    return MessageDefinitionField(
        type=final_type,
        name=field.name,
        isComplex=is_complex,
        enumType=enum_type,
        isArray=array_lengths or is_sequence,
        arrayLength=array_lengths[0] if array_lengths else None,
        arrayUpperBound=seq_bound if is_sequence else None,
    )


def _convert_constant(
    const: IDLConstant,
    typedefs: dict[str, IDLTypedef],
    scope: List[str],
    idl_map: IDLMap,
) -> MessageDefinitionField:
    t, _ = _resolve_scoped_type(const.type, scope, idl_map)
    t = _resolve_type(t, typedefs)
    return MessageDefinitionField(
        type=t,
        name=const.name,
        isConstant=True,
        value=const.value,
        valueText=str(const.value),
    )


def _normalize_name(name: str) -> str:
    return name.replace("::", "/") if "::" in name else name


def _collect_typedefs(
    defs: List[IDLStruct | IDLModule | IDLConstant | IDLEnum | IDLTypedef | IDLUnion],
    scope: List[str],
) -> dict[str, IDLTypedef]:
    typedefs: dict[str, IDLTypedef] = {}

    def collect(
        ds: List[IDLStruct | IDLModule | IDLConstant | IDLEnum | IDLTypedef | IDLUnion],
        sc: List[str],
    ):
        for d in ds:
            if isinstance(d, IDLTypedef):
                typedefs["::".join([*sc, d.name])] = d
            elif isinstance(d, IDLModule):
                collect(d.definitions, [*sc, d.name])

    collect(defs, scope)
    return typedefs


def _resolve_scoped_type(
    name: str, scope: List[str], idl_map: IDLMap
) -> tuple[str, IDLDefinition | None]:
    ref = idl_map.get(name)
    if ref is not None or "::" in name:
        return name, ref
    for i in range(len(scope), -1, -1):
        scoped = "::".join([*scope[:i], name])
        ref = idl_map.get(scoped)
        if ref is not None:
            return scoped, ref
    return name, None


def _resolve_type(name: str, typedefs: dict[str, IDLTypedef]) -> str:
    t = name
    visited: set[str] = set()
    while t in typedefs and t not in visited:
        visited.add(t)
        td = typedefs[t]
        t = td.type
    return t
