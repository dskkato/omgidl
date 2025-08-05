from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import List, Optional, Sequence, Union

# Type aliases matching the TypeScript package
ConstantValue = Optional[Union[str, int, float, bool]]
DefaultValue = Optional[
    Union[
        str,
        int,
        float,
        bool,
        Sequence[str],
        Sequence[int],
        Sequence[float],
        Sequence[bool],
    ]
]


@dataclass
class MessageDefinitionField:
    """A single field in a message definition."""

    type: str
    name: str
    isComplex: bool = False
    enumType: Optional[str] = None
    isArray: bool = False
    arrayLength: Optional[int] = None
    isConstant: bool = False
    value: ConstantValue = None
    valueText: Optional[str] = None
    upperBound: Optional[int] = None
    arrayUpperBound: Optional[int] = None
    defaultValue: DefaultValue = None


@dataclass
class MessageDefinition:
    """A message definition containing an optional name and a list of fields."""

    name: Optional[str] = None
    definitions: List[MessageDefinitionField] = dataclass_field(default_factory=list)


__all__ = [
    "ConstantValue",
    "DefaultValue",
    "MessageDefinition",
    "MessageDefinitionField",
]
