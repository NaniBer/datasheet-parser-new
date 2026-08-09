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
0.75
0.45
L
7.10
6.90
7.00
D1/E1
9.00
9.25
8.75
D/E
"""


class TestParseDimensionTable:
    def test_extracts_a1_a2_a_from_lettered_table(self):
        dims = parse_dimension_table(LETTERED_TABLE)
        assert dims["A1"] == 0.10        # (0.05 + 0.15) / 2
        assert dims["A2"] == 1.00        # (0.95 + 1.05) / 2
        assert dims["A"] == 1.20

    def test_extracts_footprint_set_from_lettered_table(self):
        dims = parse_dimension_table(LETTERED_TABLE)
        assert dims["e"] == 0.80             # "0.80 TYP." snapped to standard
        assert dims["b"] == 0.375            # (0.30 + 0.45) / 2
        assert dims["L"] == 0.60             # (0.45 + 0.75) / 2
        assert dims["D"] == 9.00             # combined "D/E" -> (8.75+9.00+9.25)/3
        assert dims["E"] == 9.00
        assert dims["E1"] == 7.00            # combined "D1/E1" -> (6.90+7.00+7.10)/3
        # Vertical profile still intact alongside the new keys.
        assert dims["A"] == 1.20
        assert dims["A1"] == 0.10
        assert dims["A2"] == 1.00

    def test_requires_table_context(self):
        # Same symbol/number pattern but no table markers -> nothing trusted.
        stray = "A1\n0.05\n0.15\nsome prose about pin A1 of the connector\n"
        assert parse_dimension_table(stray) == {}

    def test_non_table_text_returns_empty(self):
        # Prose that names symbols but carries no table markers -> {}.
        prose = "The device has an e pad and b leads described in the text.\n"
        assert parse_dimension_table(prose) == {}

    def test_symbol_then_values_order_also_works(self):
        table = "Symbol MIN MAX\nA1\n0.05\n0.15\n"
        assert parse_dimension_table(table)["A1"] == 0.10

    def test_rejects_out_of_range_standoff(self):
        # A "A1" whose adjacent value is body-scale is not a standoff -> dropped.
        table = "Symbol MIN MAX\n9.00\n9.20\nA1\n"
        assert "A1" not in parse_dimension_table(table)


class TestDualUnitAndOrientation:
    """Regression: dual-unit (mm+inch), symbol-then-values tables must not mix
    units or grab a neighbouring symbol's numbers (the STM32L031 A=A1=0.30985
    bug: averaging an inch value with a mm max)."""

    # ST-style: symbol then [mm min, mm typ, mm max, inch max]; inch column is
    # the mm value / 25.4 and must be dropped, not averaged in.
    ST_DUAL_UNIT = """\
Symbol
Min
Typ
Max
Max
A
0.500
0.550
0.600
0.0236
A1
0.000
0.020
0.050
0.0020
"""

    def test_does_not_average_mm_with_inch(self):
        dims = parse_dimension_table(self.ST_DUAL_UNIT)
        # A ~ mm column (not (0.0236 + 0.600)/2 = 0.31), A1 ~ small standoff.
        assert 0.45 <= dims["A"] <= 0.62
        assert dims["A1"] < 0.1
        # The old bug produced A == A1 == 0.30985.
        assert dims["A"] != dims.get("A1")

    def test_height_not_mislabelled_as_standoff(self):
        # A standoff column that misreads the ~0.55 height must be rejected,
        # not stored as A1 (A1 cap is 0.35mm).
        assert parse_dimension_table(self.ST_DUAL_UNIT).get("A1", 0) < 0.35

    # Symbol-then-values dual-unit footprint table: each dim carries its mm
    # value(s) then the inch equivalent (mm / 25.4), which must be dropped, not
    # averaged in, for the new footprint keys just as it is for A/A1.
    DUAL_UNIT_FOOTPRINT = """\
Symbol
Min
Max
Max
e
0.65
0.0256
b
0.40
0.0157
L
0.60
0.0236
D
9.00
0.3543
E1
7.00
0.2756
"""

    def test_footprint_keys_drop_inch_column(self):
        dims = parse_dimension_table(self.DUAL_UNIT_FOOTPRINT)
        assert dims["e"] == 0.65     # snapped standard pitch, inch 0.0256 dropped
        assert dims["b"] == 0.40     # not (0.40 + 0.0157) / 2
        assert dims["L"] == 0.60     # not (0.60 + 0.0236) / 2
        assert dims["D"] == 9.00     # not (9.00 + 0.3543) / 2
        assert dims["E1"] == 7.00    # not (7.00 + 0.2756) / 2


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
