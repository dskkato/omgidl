import unittest

from omgidl_parser.parse import parse_idl, Struct, Field
from omgidl_serialization import MessageWriter, MessageReader, EncapsulationKind


class TestMessageReader(unittest.TestCase):
    def test_roundtrip_primitive_fields(self) -> None:
        schema = """
        struct A {
            int32 num;
            uint8 flag;
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        msg = {"num": 5, "flag": 7}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_constant_field_roundtrip(self) -> None:
        const_field = Field(name="CONST", type="int32", is_constant=True, value=5)
        regular_field = Field(name="num", type="int32")
        defs = [Struct(name="A", fields=[const_field, regular_field])]
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        buf = writer.write_message({"num": 7})
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, {"CONST": 5, "num": 7})

    def test_big_endian_roundtrip(self) -> None:
        schema = """
        struct A {
            int32 num;
            uint8 flag;
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs, encapsulation_kind=EncapsulationKind.CDR_BE)
        reader = MessageReader("A", defs)
        msg = {"num": 5, "flag": 7}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_pl_cdr2_header_roundtrip(self) -> None:
        schema = """
        struct A {
            int32 num;
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs, encapsulation_kind=EncapsulationKind.PL_CDR2_LE)
        reader = MessageReader("A", defs)
        msg = {"num": 42}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_roundtrip_uint8_array(self) -> None:
        schema = """
        struct A {
            uint8 data[4];
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        msg = {"data": [1, 2, 3, 4]}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_roundtrip_string_field(self) -> None:
        schema = """
        struct A {
            string name;
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        msg = {"name": "hi"}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_roundtrip_bounded_string_field(self) -> None:
        schema = """
        struct A {
            string<5> name;
        };
        """
        defs = parse_idl(schema)
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        msg = {"name": "hello"}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_reader_bounded_string_enforced(self) -> None:
        schema_unbounded = """
        struct A {
            string name;
        };
        """
        defs_unbounded = parse_idl(schema_unbounded)
        writer = MessageWriter("A", defs_unbounded)
        buf = writer.write_message({"name": "toolong"})
        schema_bounded = """
        struct A {
            string<5> name;
        };
        """
        defs_bounded = parse_idl(schema_bounded)
        reader = MessageReader("A", defs_bounded)
        with self.assertRaises(ValueError):
            reader.read_message(buf)

    def test_roundtrip_nested_struct(self) -> None:
        inner = Struct(name="Inner", fields=[Field(name="num", type="int32")])
        outer = Struct(name="Outer", fields=[Field(name="inner", type="Inner")])
        defs = [inner, outer]
        writer = MessageWriter("Outer", defs)
        reader = MessageReader("Outer", defs)
        msg = {"inner": {"num": 5}}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_roundtrip_variable_length_sequence(self) -> None:
        defs = [Struct(name="A", fields=[Field(name="data", type="int32", is_sequence=True)])]
        writer = MessageWriter("A", defs)
        reader = MessageReader("A", defs)
        msg = {"data": [3, 7]}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)

    def test_roundtrip_sequence_of_structs(self) -> None:
        inner = Struct(name="Inner", fields=[Field(name="num", type="int32")])
        outer = Struct(name="Outer", fields=[Field(name="inners", type="Inner", is_sequence=True)])
        defs = [inner, outer]
        writer = MessageWriter("Outer", defs)
        reader = MessageReader("Outer", defs)
        msg = {"inners": [{"num": 1}, {"num": 2}]}
        buf = writer.write_message(msg)
        decoded = reader.read_message(buf)
        self.assertEqual(decoded, msg)


if __name__ == "__main__":
    unittest.main()
