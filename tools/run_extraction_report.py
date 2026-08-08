"""Corpus extraction report: package + pins + dimensions, no 3D/GLB build.

Runs the REAL pipeline (LLM page/pin extraction + dimension extraction) over
every PDF in a folder and reports, per part: detected package type, pin count,
family, and the mechanical dimensions extracted (A, A1, A2, c, D2, E2, D, E,
E1, e, b, L) with their source (text/vision/jedec) -- but stops before the
schematic/footprint/3D builders, so it isolates *data extraction* from geometry.

Robustness:
  - Each PDF runs in its own subprocess (``--one <pdf>``) with a wall-clock
    timeout, so one hung LLM call cannot stall the whole corpus.
  - A small worker pool runs several parts concurrently.
  - The vision endpoint is fast-failed (it is often down and otherwise blocks
    120s/part); dimensions therefore come from the deterministic text path.
    ``vision`` availability is recorded so the report is not mistaken for the
    full-capability number.

Usage:
  python3 tools/run_extraction_report.py [datasheets_dir] [report.json]
  python3 tools/run_extraction_report.py --one path/to/one.pdf   # worker mode
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# The code imports as ``src.*``; make the repo root importable when this file is
# run directly (python3 tools/run_extraction_report.py ...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DIM_KEYS = ["A", "A1", "A2", "c", "D2", "E2", "D", "E", "E1", "e", "b", "L"]
PER_PART_TIMEOUT = 150      # seconds; kill a stalled part and move on
WORKERS = 5                 # concurrent subprocesses


# --------------------------------------------------------------------------
# Worker mode: extract ONE pdf in-process, print a single JSON line to stdout.
# --------------------------------------------------------------------------
def _extract_one(pdf: str) -> dict:
    from unittest.mock import patch

    # Fast-fail the (frequently-down) vision endpoint so a dead qwen does not
    # block ~120s/part. Dims then come from the deterministic text path.
    def _no_vision(*a, **k):
        raise RuntimeError("vision disabled for extraction report")

    out = {"pdf": Path(pdf).name, "error": None}
    with patch("src.pdf_extractor.dimension_extractor.requests.post", _no_vision):
        import src.main as M
        from src.pdf_extractor.dimension_extractor import DimensionExtractor
        from src.package_types.footprint_defaults import _family

        ip = Path(pdf)
        model = "llama-3"
        try:
            mc = M.get_dynamic_min_confidence(ip, 5, False)
            candidates = M.detect_relevant_pages(str(ip), mc, False, model=model)
            content = M.extract_content(str(ip), candidates, False)
            part = M.infer_part_number_hint(content.text_content, source_name=ip.name)
            out["part_number"] = part

            pin_data = M.extract_pin_data(
                content, model, False, part_number=part, force_best_effort=True
            )
            try:
                M.apply_ordering_ground_truth(
                    pin_data, ip, part, model, verbose=False, force_best_effort=True
                )
            except Exception:
                pass
            try:
                M.flag_module_footprint(pin_data, ip, verbose=False)
            except Exception:
                pass
            try:
                M.enforce_known_package_type(
                    pin_data, part_number=part, package_index=None,
                    force_best_effort=False,
                )
                out["package_known"] = True
            except Exception as e:
                out["package_known"] = False
                out["enforce_note"] = str(e)[:120]

            pkg_hint, pin_count_hint, _, _ = M.pin_data_to_builder_format(
                pin_data, part_number=part, package_index=None
            )
            target = (
                pkg_hint if any(ch.isdigit() for ch in pkg_hint)
                else f"{pkg_hint}-{pin_count_hint}"
            )
            out["package_type"] = target
            out["pin_count"] = pin_count_hint
            out["family"] = _family(target) or ""
            out["module_unsupported"] = bool(
                getattr(pin_data, "footprint_unsupported_reason", None)
            )

            try:
                dims = DimensionExtractor().extract(
                    str(ip), target_package_type=target,
                    hint_pages=candidates, part_number=part,
                )
            except Exception:
                dims = None
            dims = dims or {}
            out["dims"] = {k: dims.get(k) for k in DIM_KEYS if dims.get(k) is not None}
            out["dims_source"] = dims.get("dims_source")
            out["verified_capable"] = (
                dims.get("A") is not None
                and dims.get("A1") is not None
                and dims.get("dims_source") in ("text", "vision", "text+vision")
            )
        except SystemExit as e:
            out["error"] = f"SystemExit({e.code})"
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return out


# --------------------------------------------------------------------------
# Driver mode: fan out one subprocess per PDF, collect, summarise.
# --------------------------------------------------------------------------
def _run_worker(pdf: str) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, __file__, "--one", pdf],
            capture_output=True, text=True, timeout=PER_PART_TIMEOUT,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"pdf": Path(pdf).name, "error": "no JSON emitted",
                "stderr_tail": proc.stderr.splitlines()[-1:] }
    except subprocess.TimeoutExpired:
        return {"pdf": Path(pdf).name, "error": f"timeout>{PER_PART_TIMEOUT}s"}
    except Exception as e:
        return {"pdf": Path(pdf).name, "error": f"driver:{type(e).__name__}:{e}"}


def main():
    ds_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("datasheets")
    report = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("eval_output/extraction_report.json")
    pdfs = sorted(str(p) for p in ds_dir.glob("*.pdf"))
    print(f"Extraction report over {len(pdfs)} PDFs in {ds_dir} "
          f"({WORKERS} workers, {PER_PART_TIMEOUT}s/part, vision OFF)\n")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_run_worker, p): p for p in pdfs}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            dims_n = len(r.get("dims") or {})
            vc = "V" if r.get("verified_capable") else " "
            tag = r.get("error") or f"{r.get('package_type','?'):>12} " \
                  f"pins={str(r.get('pin_count','?')):>3} dims={dims_n:>2}/12 [{vc}]"
            print(f"  [{done:3}/{len(pdfs)}] {r['pdf']:<34} {tag}")

    results.sort(key=lambda r: r["pdf"])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(results, indent=2))

    # Aggregates.
    ok = [r for r in results if not r.get("error")]
    errs = [r for r in results if r.get("error")]
    per_key = {k: sum(1 for r in ok if (r.get("dims") or {}).get(k) is not None)
               for k in DIM_KEYS}
    verified = sum(1 for r in ok if r.get("verified_capable"))
    any_dims = sum(1 for r in ok if (r.get("dims") or {}))
    fam = {}
    for r in ok:
        fam[r.get("family") or "?"] = fam.get(r.get("family") or "?", 0) + 1

    print("\n" + "=" * 60)
    print(f"parts:            {len(results)}")
    print(f"extracted ok:     {len(ok)}")
    print(f"errors/timeouts:  {len(errs)}")
    print(f"got any dims:     {any_dims}/{len(ok)}")
    print(f"verified-capable: {verified}/{len(ok)}  (has A AND A1 from text)")
    print("\nper-dimension coverage (text-only; vision was OFF):")
    for k in DIM_KEYS:
        print(f"  {k:3} {per_key[k]:>3}/{len(ok)}")
    print("\nfamily distribution:")
    for f, n in sorted(fam.items(), key=lambda kv: -kv[1]):
        print(f"  {f or '(unknown)':<10} {n}")
    print(f"\nreport written: {report}")
    if errs:
        print("\nerrors:")
        for r in errs:
            print(f"  {r['pdf']:<34} {r['error']}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--one":
        print(json.dumps(_extract_one(sys.argv[2])))
    else:
        main()
