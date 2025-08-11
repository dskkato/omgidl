from __future__ import annotations

import re
from dataclasses import replace
from typing import List

from message_definition import (
    AggregatedKind,
    Case,
    MessageDefinition,
    MessageDefinitionField,
    UnionDefinition,
)
from omgidl_parser.process import (
    IDLModuleDefinition,
    IDLStructDefinition,
    IDLUnionDefinition,
    parse_idl_message_definitions,
)

ROS2IDL_HEADER = re.compile(r"={80}\nIDL: [a-zA-Z][\w]*(?:\/[a-zA-Z][\w]*)*")


def parse_ros2idl(message_definition: str) -> List[MessageDefinition]:
    """Parse ros2idl schema into message definitions."""

    idl_conformed = ROS2IDL_HEADER.sub("", message_definition)
    idl_defs = parse_idl_message_definitions(idl_conformed)

    message_defs: List[MessageDefinition] = []
    for defn in idl_defs:
        if isinstance(defn, IDLStructDefinition):
            fields: List[MessageDefinitionField] = []
            for field in defn.definitions:
                f = replace(field)
                f.type = _normalize_name(f.type)
                if f.enumType:
                    f.enumType = _normalize_name(f.enumType)
                fields.append(f)
            message_defs.append(
                MessageDefinition(
                    name=_normalize_name(defn.name),
                    definitions=fields,
                    aggregatedKind=AggregatedKind.STRUCT,
                )
            )
        elif isinstance(defn, IDLModuleDefinition):
            fields = []
            for field in defn.definitions:
                f = replace(field)
                f.type = _normalize_name(f.type)
                if f.enumType:
                    f.enumType = _normalize_name(f.enumType)
                fields.append(f)
            message_defs.append(
                MessageDefinition(
                    name=_normalize_name(defn.name),
                    definitions=fields,
                    aggregatedKind=AggregatedKind.MODULE,
                )
            )
        elif isinstance(defn, IDLUnionDefinition):
            cases: List[Case] = []
            for c in defn.cases:
                field = replace(c.type)
                field.type = _normalize_name(field.type)
                if field.enumType:
                    field.enumType = _normalize_name(field.enumType)
                cases.append(Case(predicates=c.predicates, type=field))
            default_case = None
            if defn.defaultCase is not None:
                default_case = replace(defn.defaultCase)
                default_case.type = _normalize_name(default_case.type)
                if default_case.enumType:
                    default_case.enumType = _normalize_name(default_case.enumType)
            message_defs.append(
                MessageDefinition(
                    name=_normalize_name(defn.name),
                    aggregatedKind=AggregatedKind.UNION,
                    definitions=UnionDefinition(
                        switchType=_normalize_name(defn.switchType),
                        cases=cases,
                        defaultCase=default_case,
                    ),
                )
            )

    for msg in message_defs:
        if msg.name in (
            "builtin_interfaces/msg/Time",
            "builtin_interfaces/msg/Duration",
        ) and isinstance(msg.definitions, list):
            for field in msg.definitions:
                if field.name == "nanosec":
                    field.name = "nsec"

    return message_defs


def _normalize_name(name: str) -> str:
    s = str(name)
    return s.replace("::", "/") if "::" in s else s


__all__ = [
    "parse_ros2idl",
    "AggregatedKind",
    "MessageDefinition",
    "MessageDefinitionField",
    "UnionDefinition",
]
