from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from lark import Lark, Transformer

# A slightly larger subset grammar supporting modules, structs, constants, enums,
# typedefs and unions, with basic annotation support
IDL_GRAMMAR = r"""
start: definition+

definition: annotations? module
          | annotations? struct
          | annotations? constant
          | annotations? enum
          | annotations? typedef
          | annotations? union

module: "module" NAME "{" definition* "}" semicolon?

struct: "struct" NAME "{" field* "}" semicolon?

enum: "enum" NAME "{" enumerator ("," enumerator)* "}" semicolon?

enumerator: annotations? NAME enum_value?
enum_value: "@value" "(" INT ")"

constant: "const" type NAME "=" const_value semicolon
const_value: STRING -> const_string
           | const_atom ("+" const_atom)*

?const_atom: SIGNED_NUMBER
          | scoped_name

typedef: "typedef" type NAME array? semicolon

union: "union" NAME "switch" "(" type ")" "{" union_case+ union_default? "}" semicolon?
union_case: "case" const_value ":" field
union_default: "default" ":" field

field: annotations? type NAME array? semicolon

type: sequence_type
    | BUILTIN_TYPE
    | scoped_name

sequence_type: "sequence" "<" type ("," INT)? ">"

scoped_name: NAME ("::" NAME)*

BUILTIN_TYPE: /(unsigned\s+(short|long(\s+long)?)|long\s+double|double|float|short|long\s+long|long|int8|uint8|int16|uint16|int32|uint32|int64|uint64|byte|octet|wchar|char|string|wstring|boolean)/
NAME: /[A-Za-z_][A-Za-z0-9_]*/

array: "[" INT "]"

annotations: annotation*
annotation: "@" NAME ("(" annotation_params ")")?
annotation_params: annotation_named_params | const_value
annotation_named_params: annotation_named_param ("," annotation_named_param)*
annotation_named_param: NAME "=" const_value

semicolon: ";"

%import common.INT
%import common.SIGNED_NUMBER
%import common.ESCAPED_STRING -> STRING
%import common.WS
%ignore WS
"""

@dataclass
class Field:
    name: str
    type: str
    array_length: Optional[int] = None
    is_sequence: bool = False
    sequence_bound: Optional[int] = None
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)


@dataclass
class Constant:
    name: str
    type: str
    value: Union[int, float, str]
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)


@dataclass
class Enum:
    name: str
    enumerators: List[Constant] = field(default_factory=list)
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)

@dataclass
class Struct:
    name: str
    fields: List[Field] = field(default_factory=list)
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)

@dataclass
class Typedef:
    name: str
    type: str
    array_length: Optional[int] = None
    is_sequence: bool = False
    sequence_bound: Optional[int] = None
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)

@dataclass
class UnionCase:
    value: int | str
    field: Field

@dataclass
class Union:
    name: str
    switch_type: str
    cases: List[UnionCase] = field(default_factory=list)
    default: Optional[Field] = None
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)

@dataclass
class Module:
    name: str
    definitions: List[Struct | Module | Constant | Enum | Typedef | Union] = field(
        default_factory=list
    )
    annotations: Dict[str, "Annotation"] = field(default_factory=dict)


@dataclass
class Annotation:
    name: str
    type: str
    value: Optional[Union[int, float, str]] = None
    named_params: Dict[str, Union[int, float, str]] = field(default_factory=dict)

class _Transformer(Transformer):
    _NORMALIZATION = {
        "long double": "float64",
        "double": "float64",
        "float": "float32",
        "short": "int16",
        "unsigned short": "uint16",
        "unsigned long long": "uint64",
        "unsigned long": "uint32",
        "long long": "int64",
        "long": "int32",
    }

    _BUILTIN_TYPES = {
        "float64",
        "float32",
        "int16",
        "uint16",
        "uint64",
        "uint32",
        "int64",
        "int32",
        "int8",
        "uint8",
        "byte",
        "octet",
        "wchar",
        "char",
        "string",
        "wstring",
        "boolean",
    }

    def __init__(self):
        super().__init__()
        # Map identifiers (constants and enum values) to their evaluated numeric values
        self._constants: dict[str, int | str] = {}

    def start(self, items):
        return list(items)

    def definition(self, items):
        if len(items) == 1:
            return items[0]
        ann, node = items
        node.annotations = ann
        return node
    def NAME(self, token):
        return str(token)

    def scoped_name(self, items):
        return "::".join(items)

    def type(self, items):
        (t,) = items
        if isinstance(t, tuple) and t[0] == "sequence":
            inner, bound = t[1], t[2]
            return ("sequence", self._NORMALIZATION.get(inner, inner), bound)
        if isinstance(t, str):
            return self._NORMALIZATION.get(t, t)
        token = str(t)
        return self._NORMALIZATION.get(token, token)

    def sequence_type(self, items):
        inner = items[0]
        bound = items[1] if len(items) > 1 else None
        return ("sequence", inner, bound)

    def INT(self, token):
        return int(token)

    def SIGNED_NUMBER(self, token):
        text = str(token)
        if "." in text or "e" in text or "E" in text:
            return float(text)
        return int(text)

    def STRING(self, token):
        return str(token)[1:-1]

    def array(self, items):
        (length,) = items
        return length

    def semicolon(self, _):
        return None

    def field(self, items):
        annotations: Dict[str, Annotation] = {}
        if items and isinstance(items[0], dict):
            annotations = items[0]
            items = items[1:]
        type_, name, *rest = items
        array_length = None
        for itm in rest:
            if isinstance(itm, int):
                array_length = itm
        is_sequence = False
        sequence_bound = None
        if isinstance(type_, tuple) and type_[0] == "sequence":
            is_sequence = True
            sequence_bound = type_[2]
            type_ = type_[1]
        return Field(
            name=name,
            type=type_,
            array_length=array_length,
            is_sequence=is_sequence,
            sequence_bound=sequence_bound,
            annotations=annotations,
        )

    def const_string(self, items):
        (value,) = items
        return value

    def const_value(self, items):
        if len(items) == 1:
            item = items[0]
            if isinstance(item, (int, float)):
                return item
            if item not in self._constants:
                raise ValueError(f"Unknown identifier '{item}'")
            return self._constants[item]
        total: float | int = 0
        for idx, item in enumerate(items):
            if isinstance(item, (int, float)):
                val = item
            else:
                if item not in self._constants:
                    raise ValueError(f"Unknown identifier '{item}'")
                val = self._constants[item]
                if not isinstance(val, (int, float)):
                    raise ValueError(
                        f"Identifier '{item}' does not evaluate to a number"
                    )
            if idx == 0:
                total = val
            else:
                total += val
        return total

    def constant(self, items):
        # items: TYPE, NAME, value, None
        type_, name, value, _ = items
        const = Constant(name=name, type=type_, value=value)
        self._constants[name] = value
        return const

    def typedef(self, items):
        type_, name, *rest = items
        array_length = None
        for itm in rest:
            if isinstance(itm, int):
                array_length = itm
        is_sequence = False
        sequence_bound = None
        if isinstance(type_, tuple) and type_[0] == "sequence":
            is_sequence = True
            sequence_bound = type_[2]
            type_ = type_[1]
        return Typedef(
            name=name,
            type=type_,
            array_length=array_length,
            is_sequence=is_sequence,
            sequence_bound=sequence_bound,
        )

    def union_case(self, items):
        value, field = items
        return UnionCase(value=value, field=field)

    def union_default(self, items):
        return items[-1]

    def union(self, items):
        name = items[0]
        switch_type = items[1]
        cases: List[UnionCase] = []
        default: Optional[Field] = None
        for itm in items[2:]:
            if isinstance(itm, UnionCase):
                cases.append(itm)
            elif isinstance(itm, Field):
                default = itm
        return Union(name=name, switch_type=switch_type, cases=cases, default=default)

    def enum_value(self, items):
        (_, _, val, _) = items
        return val

    def enumerator(self, items):
        annotations: Dict[str, Annotation] = {}
        if items and isinstance(items[0], dict):
            annotations = items[0]
            items = items[1:]
        name = items[0]
        value = items[1] if len(items) > 1 else None
        return (name, value, annotations)

    def enum(self, items):
        name = items[0]
        enumerators_raw = [it for it in items[1:] if isinstance(it, tuple)]
        constants: List[Constant] = []
        current = -1
        for enum_name, enum_val, ann in enumerators_raw:
            if enum_val is not None:
                current = enum_val
            else:
                current += 1
            constants.append(
                Constant(name=enum_name, type="uint32", value=current, annotations=ann)
            )
            # Register enumerator both as unscoped and scoped (EnumName::Enumerator)
            self._constants[enum_name] = current
            self._constants[f"{name}::{enum_name}"] = current
        return Enum(name=name, enumerators=constants)

    def annotation_named_param(self, items):
        return (items[0], items[1])

    def annotation_named_params(self, items):
        return dict(items)

    def annotation_params(self, items):
        return items[0]

    def annotation(self, items):
        name = items[0]
        if len(items) == 1:
            return Annotation(name=name, type="no-params")
        params = items[1]
        if isinstance(params, dict):
            return Annotation(name=name, type="named-params", named_params=params)
        else:
            return Annotation(name=name, type="const-param", value=params)

    def annotations(self, items):
        return {ann.name: ann for ann in items}

    def struct(self, items):
        name = items[0]
        fields = [i for i in items[1:] if isinstance(i, Field)]
        return Struct(name=name, fields=fields)

    def module(self, items):
        name = items[0]
        definitions = [item for item in items[1:] if item is not None]
        return Module(name=name, definitions=definitions)

    def resolve_types(
        self, definitions: List[Struct | Module | Constant | Enum | Typedef | Union]
    ):
        named_types: set[str] = set()

        def collect(
            defs: List[Struct | Module | Constant | Enum | Typedef | Union],
            scope: List[str],
        ):
            for d in defs:
                if isinstance(d, (Struct, Union, Typedef)):
                    full = "::".join([*scope, d.name])
                    named_types.add(full)
                if isinstance(d, Module):
                    collect(d.definitions, [*scope, d.name])

        collect(definitions, [])

        def resolve_field(f: Field, scope: List[str]):
            if f.type in self._BUILTIN_TYPES:
                return
            if f.type.startswith("::"):
                f.type = f.type[2:]
                return
            if "::" in f.type:
                return
            resolved = None
            for i in range(len(scope), -1, -1):
                candidate = "::".join([*scope[:i], f.type])
                if candidate in named_types:
                    resolved = candidate
                    break
            if resolved:
                f.type = resolved

        def resolve(
            defs: List[Struct | Module | Constant | Enum | Typedef | Union],
            scope: List[str],
        ):
            for d in defs:
                if isinstance(d, Struct):
                    for f in d.fields:
                        resolve_field(f, scope)
                elif isinstance(d, Union):
                    d.switch_type = self._NORMALIZATION.get(d.switch_type, d.switch_type)
                    if (
                        d.switch_type not in self._BUILTIN_TYPES
                        and not d.switch_type.startswith("::")
                        and "::" not in d.switch_type
                    ):
                        for i in range(len(scope), -1, -1):
                            candidate = "::".join([*scope[:i], d.switch_type])
                            if candidate in named_types:
                                d.switch_type = candidate
                                break
                    for case in d.cases:
                        resolve_field(case.field, scope)
                    if d.default:
                        resolve_field(d.default, scope)
                elif isinstance(d, Typedef):
                    if (
                        d.type not in self._BUILTIN_TYPES
                        and not d.type.startswith("::")
                        and "::" not in d.type
                    ):
                        for i in range(len(scope), -1, -1):
                            candidate = "::".join([*scope[:i], d.type])
                            if candidate in named_types:
                                d.type = candidate
                                break
                elif isinstance(d, Module):
                    resolve(d.definitions, [*scope, d.name])

        resolve(definitions, [])


def parse_idl(source: str) -> List[Struct | Module | Constant | Enum | Typedef | Union]:
    parser = Lark(IDL_GRAMMAR, start="start")
    tree = parser.parse(source)
    transformer = _Transformer()
    result = transformer.transform(tree)
    transformer.resolve_types(result)
    return result

