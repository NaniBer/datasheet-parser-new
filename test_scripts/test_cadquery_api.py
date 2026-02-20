#!/usr/bin/env python3
"""Test cadquery API for schematic symbols based on universal_chip_organizer."""

import cadquery as cq


def test_assembly_and_glb_export():
    """Test creating assembly and exporting to GLB."""
    print("Testing Assembly and GLB export...")

    # Create a simple assembly
    assy = cq.Assembly(name="TestPackage")

    # Add a simple body (rectangle)
    body = cq.Workplane("XY").rect(20, 40).extrude(0.5)
    assy.add(body, name="Body", color=cq.Color(0.5, 0.5, 0.5, 1.0))

    # Add text
    text = cq.Workplane("XY").center(0, 25).text("TEST", 3.0, 0.5)
    assy.add(text, name="Label", color=cq.Color(0, 0, 0, 1.0))

    # Export to GLB
    output_path = "/tmp/test_assembly.glb"
    try:
        assy.save(output_path)
        print(f"  Exported to GLB: {output_path}")
        
        # Verify file exists
        import os
        if os.path.exists(output_path):
            print(f"  GLB file size: {os.path.getsize(output_path)} bytes")
            return True
    except Exception as e:
        print(f"  Error exporting GLB: {e}")
        return False


def test_2d_rectangles_and_positions():
    """Test creating 2D rectangles with positioning."""
    print("\nTesting 2D rectangles and positions...")

    # Create body border (wireframe style)
    body_width = 20
    body_height = 40
    thickness = 0.5

    # Top border
    top = cq.Workplane("XY").center(0, body_height / 2).rect(body_width, thickness).extrude(0.5)
    print(f"  Top border volume: {top.val().Volume()}")

    # Bottom border
    bottom = cq.Workplane("XY").center(0, -body_height / 2).rect(body_width, thickness).extrude(0.5)
    print(f"  Bottom border volume: {bottom.val().Volume()}")

    # Left border
    left = cq.Workplane("XY").center(-body_width / 2, 0).rect(thickness, body_height).extrude(0.5)
    print(f"  Left border volume: {left.val().Volume()}")

    # Right border
    right = cq.Workplane("XY").center(body_width / 2, 0).rect(thickness, body_height).extrude(0.5)
    print(f"  Right border volume: {right.val().Volume()}")

    # Combine borders
    borders = top.union(bottom).union(left).union(right)
    print(f"  Combined borders volume: {borders.val().Volume()}")

    return True


def test_text_creation():
    """Test creating text with different alignments."""
    print("\nTesting text creation...")

    # Left-aligned text
    left_txt = cq.Workplane("XY").center(-5, 10).text("LEFT", 2.0, 0.5, halign="left")
    print(f"  Left-aligned text volume: {left_txt.val().Volume()}")

    # Right-aligned text
    right_txt = cq.Workplane("XY").center(5, 10).text("RIGHT", 2.0, 0.5, halign="right")
    print(f"  Right-aligned text volume: {right_txt.val().Volume()}")

    # Center-aligned text
    center_txt = cq.Workplane("XY").center(0, 5).text("CENTER", 2.0, 0.5, halign="center")
    print(f"  Center-aligned text volume: {center_txt.val().Volume()}")

    return True


def test_pin_leg_geometry():
    """Test creating pin leg geometry."""
    print("\nTesting pin leg geometry...")

    # Pin leg - thin rectangle
    pin_leg = cq.Workplane("XY").center(10, 0).rect(6, 0.15).extrude(0.5)
    print(f"  Pin leg volume: {pin_leg.val().Volume()}")

    # Pin point (small circle/point at end)
    # Can use a small cylinder or box as a point
    pin_point = cq.Workplane("XY").center(13, 0).box(0.5, 0.5, 0.5)
    print(f"  Pin point volume: {pin_point.val().Volume()}")

    return True


def test_assembly_hierarchy():
    """Test assembly hierarchy matching universal_chip_organizer."""
    print("\nTesting assembly hierarchy...")

    # Main package assembly
    package_assy = cq.Assembly(name="Package")

    # BodyLine sub-assembly for borders
    body_line_assy = cq.Assembly(name="BodyLine")
    top = cq.Workplane("XY").center(0, 10).rect(20, 0.5).extrude(0.5)
    bottom = cq.Workplane("XY").center(0, -10).rect(20, 0.5).extrude(0.5)
    body_line_assy.add(top, name="BodyLine_Top", color=cq.Color(0, 0, 0, 1.0))
    body_line_assy.add(bottom, name="BodyLine_Bottom", color=cq.Color(0, 0, 0, 1.0))

    # Add BodyLine to Package
    package_assy.add(body_line_assy, name="BodyLine")

    # Legs sub-assembly for pins
    legs_assy = cq.Assembly(name="Legs")
    pin1 = cq.Workplane("XY").center(-12, 5).rect(4, 0.15).extrude(0.5)
    legs_assy.add(pin1, name="pin1", color=cq.Color(0.34, 0.13, 0.44, 1.0))

    # Add Legs to Package
    package_assy.add(legs_assy, name="Legs")

    # Add designator
    designator = cq.Workplane("XY").center(0, 15).text("U", 3.0, 0.5)
    package_assy.add(designator, name="DesignatorName", color=cq.Color(0, 0, 0, 1.0))

    print(f"  Package assembly created with {len(package_assy.children)} top-level children")

    # Export to GLB
    output_path = "/tmp/test_hierarchy.glb"
    package_assy.save(output_path)
    print(f"  Exported to GLB: {output_path}")

    import os
    if os.path.exists(output_path):
        print(f"  GLB file size: {os.path.getsize(output_path)} bytes")

    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Cadquery API Test for Schematic Symbols")
    print("=" * 60)

    test_assembly_and_glb_export()
    test_2d_rectangles_and_positions()
    test_text_creation()
    test_pin_leg_geometry()
    test_assembly_hierarchy()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
