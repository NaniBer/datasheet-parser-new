"""Part-number inference must not mistake a package/case label for a part number.

On a pin-configuration page, package labels like "DFN-6" or "SOIC-8" can
out-score the real part number in the token ranking. When the ordered part
number is absent from the extracted text, the inferer would then return the
package (observed: MCP1700's hint resolved to "DFN-6"), which drives the wrong
package variant downstream. Package labels are rejected as candidates.
"""
from src.pdf_extractor.part_number_hint import (
    _token_is_plausible,
    infer_part_number_hint,
)


class TestPackageLabelRejected:
    def test_common_package_labels_are_not_plausible(self):
        for label in [
            "DFN-6", "SOIC-8", "TO-92", "SOT-23", "SOT-223", "QFN-32",
            "TQFP-44", "LQFP-64", "DIP-8", "PDIP-16", "BGA-64", "SON-8",
            "WSON-8", "TSSOP-20", "DO-214AC", "DPAK",
        ]:
            assert _token_is_plausible(label) is False, label

    def test_real_part_numbers_still_plausible(self):
        for pn in [
            "MCP1700T", "AD636JHZ", "TPS23751PWP", "W25Q128JVSIM", "STM32L031",
            "LM2673", "SN74HC595DW", "INA238", "ATTINY13A", "DS3231",
        ]:
            assert _token_is_plausible(pn) is True, pn

    def test_package_label_not_returned_as_hint(self):
        # A page dominated by a package label plus a corroborated real part
        # number: the part number wins, never the package label.
        text = (
            "=== Page 1 ===\n"
            "MCP1700 Low Dropout Regulator\n"
            "Pin Configuration DFN-6\n"
            "DFN-6 DFN-6 DFN-6\n"
            "MCP1700\n"
        )
        hint = infer_part_number_hint(text, source_name="102_MCP1700T-3002E-MB.pdf")
        assert hint is not None
        assert "DFN" not in hint  # never the package label
