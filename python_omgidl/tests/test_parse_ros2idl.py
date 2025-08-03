import unittest

from ros2idl_parser import parse_ros2idl, MessageDefinition, MessageDefinitionField


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
                            isArray=False,
                        )
                    ],
                ),
            ],
        )

    def test_union(self):
        schema = """
        module pkg {
          module msg {
            union Foo switch (uint8) {
              case 0: int32 i;
              case 1: float32 f;
            };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="pkg/msg/Foo",
                    definitions=[
                        MessageDefinitionField(type="uint8", name="_type"),
                        MessageDefinitionField(type="int32", name="i"),
                        MessageDefinitionField(type="float32", name="f"),
                    ],
                )
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

    def test_typedef(self):
        schema = """
        module pkg {
          module msg {
            typedef int32 MyInt;
            struct A { MyInt value; };
          };
        };
        """
        types = parse_ros2idl(schema)
        self.assertEqual(
            types,
            [
                MessageDefinition(
                    name="pkg/msg/A",
                    definitions=[
                        MessageDefinitionField(type="int32", name="value")
                    ],
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
