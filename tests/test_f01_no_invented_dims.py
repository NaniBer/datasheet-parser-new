"""F-01: no dimension invented — unresolved/approximated dims are FLAGGED, and
flagged output STOPS (degraded exit; --strict refuses).

F-01 is a pipeline-behaviour contract, not a static-artifact property, so it is
covered by this deterministic gate test rather than a conformance check (it stays
UNRUN in the static matrix, like the build-time rules). No LLM involved.
"""
import pytest

import src.main as main_mod
from src.models.pin_data import PinData


# --- flag: unresolved dims are recorded, never silently invented -------------
def test_record_degraded_flags_and_dedupes():
    pd = PinData(component_name="X")
    assert not pd.validation_errors
    main_mod._record_degraded(pd, ["no verified body height; used JEDEC default"])
    assert pd.validation_errors == ["no verified body height; used JEDEC default"]
    main_mod._record_degraded(pd, ["no verified body height; used JEDEC default"])
    assert pd.validation_errors.count("no verified body height; used JEDEC default") == 1


# --- stop: flagged output exits degraded, clean output does not --------------
def test_flagged_output_exits_degraded():
    pd = PinData(component_name="X", validation_errors=["unverified geometry"])
    with pytest.raises(SystemExit) as exc:
        main_mod._exit_if_degraded(pd)
    assert exc.value.code == main_mod.EXIT_DEGRADED


def test_clean_output_does_not_exit():
    main_mod._exit_if_degraded(PinData(component_name="X"))  # no validation_errors
    main_mod._exit_if_degraded(None)                          # nothing to check


# --- strict restores fail-closed (refuse rather than emit best-effort) -------
def test_strict_restores_fail_closed():
    assert main_mod._resolve_best_effort(force_best_effort=False, strict=False) is True
    assert main_mod._resolve_best_effort(force_best_effort=False, strict=True) is False


# --- real generation flags approximated geometry instead of inventing it -----
def test_footprint_flags_approximated_geometry():
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
    # MSOP-10 has no dedicated geometry: it is approximated AND flagged.
    approx = PcbFootprintBuilder("MSOP-10", 10, "X")
    assert approx.degraded_reasons, "approximated geometry must be flagged"
    assert any("approximated" in r.lower() for r in approx.degraded_reasons)
    # A family with real JEDEC defaults declares its source and is not degraded.
    sourced = PcbFootprintBuilder("SOIC-8", 8, "X")
    assert sourced.dims_source == "jedec_default"
    assert sourced.degraded_reasons == []
