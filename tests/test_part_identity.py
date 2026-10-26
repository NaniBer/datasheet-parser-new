"""Part identity metadata (QC re-check C1): manufacturer, description, footprint name."""

import json
from pathlib import Path

import pytest

from src.pdf_extractor.part_identity import (
    PartIdentity,
    detect_manufacturer,
    footprint_names,
    llm_description,
    numbers_grounded,
    page1_title,
    resolve_part_identity,
)

_LVC_PDF = Path(__file__).parent / "ground_truth" / "74LVC1G99_rev13.pdf"


# --------------------------------------------------------------------------- #
# Manufacturer
# --------------------------------------------------------------------------- #

def test_manufacturer_from_copyright_line():
    pages = ["Quad DAC\nwww.analog.com", "...", "©2012–2013 Analog Devices, Inc. All rights reserved."]
    assert detect_manufacturer(pages, {}) == ("Analog Devices", "copyright")


def test_mirror_site_author_is_ignored():
    pages = ["2.5-V to 5-V DUAL UART", "© 2005, Texas Instruments Incorporated"]
    meta = {"author": "Provided By ALLDATASHEET.COM(FREE DATASHEET DOWNLOAD SITE)"}
    assert detect_manufacturer(pages, meta)[0] == "Texas Instruments"


def test_acquired_brand_maps_to_current_owner():
    pages = ["Copyright © 2010 Linear Technology Corporation"]
    assert detect_manufacturer(pages, {})[0] == "Analog Devices"


@pytest.mark.parametrize("pn,expected", [
    ("74LVC1G99GT,115", "Nexperia"),     # NXP standard logic went to Nexperia
    ("HEF4051BT", "Nexperia"),
    ("PCF8574T", "NXP Semiconductors"),  # NXP still makes this one
])
def test_old_nxp_logic_datasheet_is_nexperia(pn, expected):
    pages = ["Product data sheet", "© NXP B.V. 2008. All rights reserved."]
    assert detect_manufacturer(pages, {}, pn)[0] == expected


def test_no_vendor_found():
    assert detect_manufacturer(["some text"], {}) == (None, None)


# --------------------------------------------------------------------------- #
# Page-1 title (description fallback)
# --------------------------------------------------------------------------- #

def _line(text, size, y):
    return {"bbox": [50, y, 500, y + size],
            "spans": [{"text": text, "size": size}]}


def test_title_skips_part_number_heading_and_joins_hyphen_break():
    page = {"blocks": [{"lines": [
        _line("Quad, Low Power, 12-Bit, 180 MSPS, Digital-to-", 20.0, 46),
        _line("Analog Converter and Waveform Generator", 22.5, 67),
        _line("AD9106", 22.5, 96),             # part number (single token)
        _line("Data Sheet", 17.0, 99),          # heading
        _line("FEATURES", 11.0, 135),
    ]}]}
    assert page1_title(page, 792) == (
        "Quad, Low Power, 12-Bit, 180 MSPS, Digital-to-Analog Converter and Waveform Generator"
    )


def test_title_skips_company_name_and_drawing_labels():
    page = {"blocks": [{"lines": [
        _line("Bridgetek Pte Ltd", 22.0, 103),
        _line("Dimensions: [mm]", 22.0, 37),
        _line("(Advanced Embedded Video Engine)", 12.0, 161),
    ]}]}
    assert page1_title(page, 842) == "Advanced Embedded Video Engine"


# --------------------------------------------------------------------------- #
# LLM description: numbers must be grounded in the datasheet
# --------------------------------------------------------------------------- #

_SOURCE = ["Quad, Low Power, 12-Bit, 180 MSPS, Digital-to-Analog Converter. © Analog Devices"]


def _fake(answer):
    return lambda messages: json.dumps(answer)


def test_numbers_grounded():
    assert numbers_grounded("Quad 12-bit 180 MSPS DAC", _SOURCE[0])
    assert not numbers_grounded("Quad 16-bit 180 MSPS DAC", _SOURCE[0])
    assert not numbers_grounded("Quad 12-bit 18 MSPS DAC", _SOURCE[0])  # 18 is not 180


def test_llm_description_accepted_when_grounded():
    desc, mfr = llm_description(
        _SOURCE, "AD9106BCPZ",
        _fake({"description": "Quad 12-bit 180 MSPS DAC.", "manufacturer": "Analog Devices"}),
    )
    assert desc == "Quad 12-bit 180 MSPS DAC" and mfr == "Analog Devices"


@pytest.mark.parametrize("bad", [
    "Quad 16-bit 250 MSPS DAC",                 # invented numbers
    "AD9106BCPZ quad DAC",                      # repeats the part number
    "AD9106 (created from datasheet)",          # the platform placeholder
    "x" * 150,                                  # not one line
])
def test_llm_description_rejected(bad):
    desc, _ = llm_description(_SOURCE, "AD9106BCPZ", _fake({"description": bad}))
    assert desc is None


def test_llm_garbage_answer_is_ignored():
    desc, mfr = llm_description(_SOURCE, "X", lambda m: "sorry, I can't")
    assert desc is None and mfr is None


# --------------------------------------------------------------------------- #
# Footprint name
# --------------------------------------------------------------------------- #

def test_footprint_names():
    assert footprint_names("TQFP-48", 48, body_w=7, body_l=7, pitch=0.5) == (
        "TQFP-48_7x7mm_P0.5mm", "TQFP-48")
    assert footprint_names("LFCSP-32", 32, body_w=5, body_l=5, pitch=0.5,
                           epad=(3.75, 3.75))[0] == "LFCSP-32_5x5mm_P0.5mm_EP3.75mm"
    assert footprint_names("PDIP-16", 16, row_spacing=7.62, through_hole=True)[0] == (
        "PDIP-16_W7.62mm")
    assert footprint_names("XSON8", 8, body_w=1, body_l=1.95, pitch=0.5)[0] == (
        "XSON-8_1x1.95mm_P0.5mm_SOT833-1")
    assert footprint_names("", 8) == (None, None)


def test_extras_use_platform_property_names():
    ident = PartIdentity(manufacturer="Nexperia", description="Configurable gate, XSON-8",
                         footprint_name="XSON-8_1x1.95mm_P0.5mm_SOT833-1",
                         supplier_footprint="XSON-8", mpn="74LVC1G99GT,115",
                         sources={"manufacturer": "copyright"})
    extras = ident.to_extras()
    assert set(extras) == {"manufacturer", "description", "footprintName",
                           "supplierFootprint", "manufacturerPartNumber", "identitySource"}
    assert PartIdentity().to_extras() == {}


# --------------------------------------------------------------------------- #
# End to end on a real datasheet (no network: fake LLM)
# --------------------------------------------------------------------------- #

def test_resolve_on_real_datasheet_with_llm():
    ident = resolve_part_identity(
        str(_LVC_PDF), "74LVC1G99GT,115",
        complete=_fake({"description": "Ultra-configurable multiple function gate, 3-state output",
                        "manufacturer": "Nexperia"}),
        footprint=("XSON-8_1x1.95mm_P0.5mm_SOT833-1", "XSON-8"),
    )
    assert ident.manufacturer == "Nexperia"
    assert ident.description == "Ultra-configurable multiple function gate, 3-state output, XSON-8"
    assert ident.sources["description"] == "llm"
    assert ident.mpn == "74LVC1G99GT,115"


def test_resolve_falls_back_to_title_without_llm():
    ident = resolve_part_identity(str(_LVC_PDF), "74LVC1G99GT,115", complete=None)
    assert ident.description == "Ultra-configurable multiple function gate; 3-state"
    assert ident.sources["description"] == "title"


def test_resolve_falls_back_to_title_when_llm_fails():
    def boom(messages):
        raise RuntimeError("no API key")
    ident = resolve_part_identity(str(_LVC_PDF), "74LVC1G99GT,115", complete=boom)
    assert ident.sources["description"] == "title" and ident.manufacturer == "Nexperia"


def test_resolve_never_raises_on_missing_pdf():
    ident = resolve_part_identity("/nonexistent.pdf", "X", footprint=("A", "B"))
    assert ident.footprint_name == "A" and ident.description is None


# --------------------------------------------------------------------------- #
# GLB writer
# --------------------------------------------------------------------------- #

def test_inject_part_identity_writes_package_node(tmp_path):
    pygltflib = pytest.importorskip("pygltflib")
    from src.core.part_identity_extras import inject_part_identity

    gltf = pygltflib.GLTF2(
        scene=0,
        scenes=[pygltflib.Scene(nodes=[0])],
        nodes=[pygltflib.Node(name="Package", extras={"viewType": "2d"})],
    )
    path = str(tmp_path / "x.glb")
    gltf.save_binary(path)

    assert inject_part_identity(path, {"manufacturer": "Texas Instruments"})
    extras = pygltflib.GLTF2().load_binary(path).nodes[0].extras
    assert extras == {"viewType": "2d", "manufacturer": "Texas Instruments"}
    assert not inject_part_identity(path, {})
