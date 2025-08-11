import unittest

from ros2idl_parser import (
    AggregatedKind,
    Case,
    MessageDefinition,
    MessageDefinitionField,
    UnionDefinition,
    parse_ros2idl,
)


class TestParseRos2idl(unittest.TestCase):
    def test_module_with_struct_and_constants(self):
        schema = """
        module rosidl_parser {
          module action {
            module MyAction_Goal_Constants {
              const short SHORT_CONSTANT = -23;
            };
            struct MyAction_Goal {
              int32 input_value;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="rosidl_parser/action/MyAction_Goal_Constants",
                    aggregatedKind=AggregatedKind.MODULE,
                    definitions=[
                        MessageDefinitionField(
                            type="int16",
                            name="SHORT_CONSTANT",
                            isConstant=True,
                            value=-23,
                            valueText="-23",
                        )
                    ],
                ),
                MessageDefinition(
                    name="rosidl_parser/action/MyAction_Goal",
                    definitions=[
                        MessageDefinitionField(
                            type="int32",
                            name="input_value",
                        )
                    ],
                ),
            ],
        )

    def test_builtin_time_normalization(self):
        schema = """
        module builtin_interfaces {
          module msg {
            struct Time {
              int32 sec;
              uint32 nanosec;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="builtin_interfaces/msg/Time",
                    definitions=[
                        MessageDefinitionField(type="int32", name="sec"),
                        MessageDefinitionField(type="uint32", name="nsec"),
                    ],
                )
            ],
        )

    def test_sequence_field(self):
        schema = """
        module pkg {
          module msg {
            struct Seq {
              sequence<int32> data;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="pkg/msg/Seq",
                    definitions=[
                        MessageDefinitionField(type="int32", name="data", isArray=True)
                    ],
                )
            ],
        )

    def test_bounded_sequence_field(self):
        schema = """
        module pkg {
          module msg {
            struct Seq {
              sequence<int32, 7> data;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="pkg/msg/Seq",
                    definitions=[
                        MessageDefinitionField(
                            type="int32",
                            name="data",
                            isArray=True,
                            arrayUpperBound=7,
                        )
                    ],
                )
            ],
        )

    def test_nested_enum_field(self):
        schema = """
        module test_interfaces {
          module msg {
            module TestMessage_Enums {
              enum TestEnum { OK, ERROR, FATAL };
            };
            struct TestMessage {
              TestMessage_Enums::TestEnum error;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types[-1],
            MessageDefinition(
                name="test_interfaces/msg/TestMessage",
                definitions=[
                    MessageDefinitionField(
                        type="uint32",
                        name="error",
                        enumType="test_interfaces/msg/TestMessage_Enums/TestEnum",
                    )
                ],
            ),
        )

    def test_typedef_resolution(self):
        schema = """
        typedef long MyLong;
        struct Holder { MyLong data; };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="Holder",
                    definitions=[MessageDefinitionField(type="int32", name="data")],
                )
            ],
        )

    def test_struct_field_is_complex(self):
        schema = """
        module rosidl_parser {
          module msg {
            struct MyMessage {
              geometry::msg::Point single_point;
            };
          };
        };
        module geometry {
          module msg {
            struct Point { float x; };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="rosidl_parser/msg/MyMessage",
                    definitions=[
                        MessageDefinitionField(
                            type="geometry/msg/Point",
                            name="single_point",
                            isComplex=True,
                        )
                    ],
                ),
                MessageDefinition(
                    name="geometry/msg/Point",
                    definitions=[MessageDefinitionField(type="float32", name="x")],
                ),
            ],
        )

    def test_enum_reference(self):
        schema = """
        enum COLORS {
          RED,
          GREEN,
          BLUE
        };
        struct Line { COLORS color; };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="COLORS",
                    aggregatedKind=AggregatedKind.MODULE,
                    definitions=[
                        MessageDefinitionField(
                            type="uint32",
                            name="RED",
                            isConstant=True,
                            value=0,
                            valueText="0",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="GREEN",
                            isConstant=True,
                            value=1,
                            valueText="1",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="BLUE",
                            isConstant=True,
                            value=2,
                            valueText="2",
                        ),
                    ],
                ),
                MessageDefinition(
                    name="Line",
                    definitions=[
                        MessageDefinitionField(
                            type="uint32", name="color", enumType="COLORS"
                        )
                    ],
                ),
            ],
        )

    def test_scoped_enum_reference(self):
        schema = """
        module colors {
          enum Palette {
            RED,
            GREEN
          };
        };
        struct Pixel { colors::Palette tone; };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="colors/Palette",
                    aggregatedKind=AggregatedKind.MODULE,
                    definitions=[
                        MessageDefinitionField(
                            type="uint32",
                            name="RED",
                            isConstant=True,
                            value=0,
                            valueText="0",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="GREEN",
                            isConstant=True,
                            value=1,
                            valueText="1",
                        ),
                    ],
                ),
                MessageDefinition(
                    name="Pixel",
                    definitions=[
                        MessageDefinitionField(
                            type="uint32", name="tone", enumType="colors/Palette"
                        )
                    ],
                ),
            ],
        )

    def test_union_definition(self):
        schema = """
        module test_msgs {
          enum TestDataType {
            INT,
            STR,
            FLOAT
          };
          union TestData switch(TestDataType) {
            case INT: long as_int;
            case STR: string<255> as_string;
            case FLOAT: double as_float;
          };
          module msg {
            struct TestMessage {
              string<64> label;
              TestData data;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="test_msgs/TestDataType",
                    aggregatedKind=AggregatedKind.MODULE,
                    definitions=[
                        MessageDefinitionField(
                            type="uint32",
                            name="INT",
                            isConstant=True,
                            value=0,
                            valueText="0",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="STR",
                            isConstant=True,
                            value=1,
                            valueText="1",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="FLOAT",
                            isConstant=True,
                            value=2,
                            valueText="2",
                        ),
                    ],
                ),
                MessageDefinition(
                    name="test_msgs/TestData",
                    aggregatedKind=AggregatedKind.UNION,
                    definitions=UnionDefinition(
                        switchType="uint32",
                        cases=[
                            Case(
                                predicates=[0],
                                type=MessageDefinitionField(
                                    type="int32",
                                    name="as_int",
                                ),
                            ),
                            Case(
                                predicates=[1],
                                type=MessageDefinitionField(
                                    type="string",
                                    name="as_string",
                                    upperBound=255,
                                ),
                            ),
                            Case(
                                predicates=[2],
                                type=MessageDefinitionField(
                                    type="float64",
                                    name="as_float",
                                ),
                            ),
                        ],
                    ),
                ),
                MessageDefinition(
                    name="test_msgs/msg/TestMessage",
                    definitions=[
                        MessageDefinitionField(
                            type="string", name="label", upperBound=64
                        ),
                        MessageDefinitionField(
                            type="test_msgs/TestData", name="data", isComplex=True
                        ),
                    ],
                ),
            ],
        )

    def test_union_with_default_case(self):
        schema = """\
        module test_msgs {
          enum ShapeType {
            SPHERE,
            BOX
          };
          union Shape switch(ShapeType) {
            case SPHERE: double radius;
            default: double side;
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="test_msgs/ShapeType",
                    aggregatedKind=AggregatedKind.MODULE,
                    definitions=[
                        MessageDefinitionField(
                            type="uint32",
                            name="SPHERE",
                            isConstant=True,
                            value=0,
                            valueText="0",
                        ),
                        MessageDefinitionField(
                            type="uint32",
                            name="BOX",
                            isConstant=True,
                            value=1,
                            valueText="1",
                        ),
                    ],
                ),
                MessageDefinition(
                    name="test_msgs/Shape",
                    aggregatedKind=AggregatedKind.UNION,
                    definitions=UnionDefinition(
                        switchType="uint32",
                        cases=[
                            Case(
                                predicates=[0],
                                type=MessageDefinitionField(
                                    type="float64",
                                    name="radius",
                                ),
                            )
                        ],
                        defaultCase=MessageDefinitionField(
                            type="float64",
                            name="side",
                        ),
                    ),
                ),
            ],
        )

    def test_multi_dimensional_array_not_supported(self):
        schema = """
        struct MultiArray { int32 data[3][5]; };
        """
        with self.assertRaises(ValueError):
            parse_ros2idl(schema)


if __name__ == "__main__":
    unittest.main()
