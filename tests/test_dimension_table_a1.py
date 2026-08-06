"""Tests for the lettered dimension-table parser (standoff A1 / body A2).

The graphical TI-outline parser reads the X/Y footprint but not the Z standoff
A1, because A1's label lives in the drawing graphic, not the text layer. Many
Microchip/Atmel datasheets instead print a lettered "Dimension Limits" /
"COMMON DIMENSIONS" table where every JEDEC symbol carries explicit MIN/NOM/MAX
values; parse_dimension_table reads A1/A2 (and A) from those.
"""
from src.pdf_extractor.text_dimensions import parse_dimension_table, plausible_dims


# A lettered table as it text-extracts (two-column flow -> values then symbol),
# mirroring the ATmega328P TQFP "COMMON DIMENSIONS" page.
LETTERED_TABLE = """\
COMMON DIMENSIONS
(Unit of Measure = mm)
MIN
NOM
MAX
NOTE
Symbol
1.20
A
0.15
0.05
A1
1.05
0.95
1.00
A2
0.20
0.09
C
0.45
0.30
b
0.80 TYP.
e
"""


class TestParseDimensionTable:
    def test_extracts_a1_a2_a_from_lettered_table(self):
        dims = parse_dimension_table(LETTERED_TABLE)
        assert dims["A1"] == 0.10        # (0.05 + 0.15) / 2
        assert dims["A2"] == 1.00        # (0.95 + 1.05) / 2
        assert dims["A"] == 1.20

    def test_requires_table_context(self):
        # Same symbol/number pattern but no table markers -> nothing trusted.
        stray = "A1\n0.05\n0.15\nsome prose about pin A1 of the connector\n"
        assert parse_dimension_table(stray) == {}

    def test_symbol_then_values_order_also_works(self):
        table = "Symbol MIN MAX\nA1\n0.05\n0.15\n"
        assert parse_dimension_table(table)["A1"] == 0.10

    def test_rejects_out_of_range_standoff(self):
        # A "A1" whose adjacent value is body-scale is not a standoff -> dropped.
        table = "Symbol MIN MAX\n9.00\n9.20\nA1\n"
        assert "A1" not in parse_dimension_table(table)


class TestPlausibilityA1A2:
    def test_accepts_valid_vertical_profile(self):
        assert plausible_dims({"A": 1.2, "A1": 0.1, "A2": 1.0}) is True

    def test_rejects_oversized_standoff(self):
        assert plausible_dims({"A1": 1.0}) is False

    def test_rejects_body_taller_than_overall(self):
        assert plausible_dims({"A": 1.0, "A2": 1.5}) is False

    def test_a1_absent_is_still_plausible(self):
        # Optional: absence must not change the gate.
        assert plausible_dims({"A": 1.2, "e": 0.8, "b": 0.4}) is True
