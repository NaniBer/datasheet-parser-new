"""Test specialized table prompt on multiple PDFs."""

import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_pdf(pdf_path: str):
    """Test a single PDF with the new table prompt."""
    import subprocess

    print(f"\n{'=' * 70}")
    print(f"TESTING: {Path(pdf_path).name}")
    print(f"{'=' * 70}")

    output_file = f"output/test_{Path(pdf_path).stem}_specialized.glb"

    # Run the main script
    cmd = [
        "python3", "-m", "src.main",
        pdf_path, output_file,
        "--verbose"
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180
    )

    # Extract key information
    output = result.stdout + result.stderr

    # Look for extraction results
    lines = output.split('\n')

    component = "Not found"
    package = "Not found"
    pin_count = "Not found"
    pins = []

    for i, line in enumerate(lines):
        if "Component:" in line:
            component = line.split("Component:")[-1].strip()
        elif "Package:" in line and "Pin count:" not in line:
            package = line.split("Package:")[-1].strip()
        elif "Pin count:" in line:
            pin_count = line.split("Pin count:")[-1].strip()
        elif "Pin " in line and ":" in line and "pins:" not in line:
            # Parse pin line: "   1. Pin 1:  QB (output)"
            parts = line.split(":")
            if len(parts) > 1:
                pin_info = parts[1].strip()
                pins.append(pin_info)

    # Display results
    print(f"\nResults:")
    print(f"  Component: {component}")
    print(f"  Package: {package}")
    print(f"  Pin count: {pin_count}")
    print(f"  Number of pins extracted: {len(pins)}")

    if len(pins) <= 10:
        print(f"\n  All pins:")
        for pin in pins:
            print(f"    {pin}")
    else:
        print(f"\n  First 5 pins:")
        for pin in pins[:5]:
            print(f"    {pin}")
        print(f"  ... and {len(pins) - 5} more")

    # Check for success indicators
    success = True
    issues = []

    if component == "Unknown":
        success = False
        issues.append("Component name not detected")

    if "Not found" in pin_count:
        success = False
        issues.append("Pin count not detected")

    if len(pins) == 0:
        success = False
        issues.append("No pins extracted")

    # Check for duplicates
    pin_numbers = []
    for pin in pins:
        if ":" in pin:
            num = pin.split(":")[0].strip()
            if num.isdigit():
                pin_numbers.append(int(num))

    if len(pin_numbers) != len(set(pin_numbers)):
        success = False
        issues.append("Duplicate pin numbers detected")

    print(f"\nStatus: {'✅ SUCCESS' if success else '❌ FAILED'}")
    if issues:
        print(f"Issues: {', '.join(issues)}")

    return {
        "pdf": Path(pdf_path).name,
        "component": component,
        "package": package,
        "pin_count": pin_count,
        "num_pins": len(pins),
        "success": success,
        "issues": issues
    }

def main():
    """Test multiple PDFs."""
    pdfs = [
        "pdfs/74HC595_TI.pdf",      # Multi-variant table (SOIC/PDIP/LCCC)
        "pdfs/AMS1117.pdf",          # Simple voltage regulator
        "pdfs/esp32-c3_datasheet_en.pdf",  # Complex MCU
        "pdfs/MAX1487-MAX491.pdf",   # Communication chip
        "pdfs/MPU-6000-Datasheet1.pdf",  # Gyro/accelerometer
    ]

    results = []

    for pdf in pdfs:
        if Path(pdf).exists():
            try:
                result = test_pdf(pdf)
                results.append(result)
            except Exception as e:
                print(f"\n❌ Error testing {pdf}: {e}")
                results.append({
                    "pdf": Path(pdf).name,
                    "error": str(e)
                })
        else:
            print(f"\n❌ File not found: {pdf}")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    successful = [r for r in results if r.get("success", False)]
    failed = [r for r in results if not r.get("success", False)]

    print(f"\nTotal tested: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")

    if successful:
        print(f"\n✅ Successful PDFs:")
        for r in successful:
            print(f"  - {r['pdf']}: {r['component']} ({r['package']}) - {r['num_pins']} pins")

    if failed:
        print(f"\n❌ Failed PDFs:")
        for r in failed:
            if "error" in r:
                print(f"  - {r['pdf']}: ERROR - {r['error']}")
            else:
                print(f"  - {r['pdf']}: {', '.join(r.get('issues', ['Unknown error']))}")

if __name__ == "__main__":
    main()
