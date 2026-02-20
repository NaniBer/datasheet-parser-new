#!/usr/bin/env python3
"""Test cadquery installation and GLB export."""

import cadquery as cq
import trimesh
import numpy as np


def test_cadquery_basic():
    """Test basic cadquery functionality."""
    print("Testing basic cadquery...")

    # Create a simple rectangle (2D)
    result = cq.Workplane('XY').rect(10, 5)
    print(f"Created rectangle: {result}")
    print(f"  Area: {result.val().Area()}")

    # Create a 3D box
    box = cq.Workplane('XY').box(5, 5, 2)
    print(f"Created box: {box}")
    print(f"  Volume: {box.val().Volume()}")

    return True


def test_cadquery_to_trimesh():
    """Test converting cadquery shape to trimesh and exporting to GLB."""
    print("\nTesting cadquery to trimesh conversion...")

    # Create a simple 3D box
    box = cq.Workplane('XY').box(10, 5, 1)

    # Convert to trimesh using STL export
    # Export to STL first, then load with trimesh
    stl_path = '/tmp/test_box.stl'
    box.val().exportStl(stl_path)

    # Load STL with trimesh
    mesh = trimesh.load(stl_path)
    print(f"Loaded STL into trimesh: {mesh}")

    # Export to GLB
    glb_path = '/tmp/test_box.glb'
    mesh.export(glb_path)
    print(f"Exported to GLB: {glb_path}")

    # Verify GLB file exists
    import os
    if os.path.exists(glb_path):
        print(f"  GLB file size: {os.path.getsize(glb_path)} bytes")

        # Load and verify
        loaded = trimesh.load(glb_path)
        print(f"  Reloaded GLB: {loaded}")
        return True
    return False


def test_2d_geometry_for_schematic():
    """Test creating 2D geometry for schematic symbols."""
    print("\nTesting 2D geometry for schematic symbols...")

    # Create a simple rectangular body (like IC body)
    # Body: 10mm x 20mm
    body = cq.Workplane('XY').rect(10, 20)
    print(f"Created IC body: {body}")

    # Create pin leg (line)
    # Pin leg: 5mm long, 0.5mm wide
    # Note: For 2D lines, we can use workplane operations
    pin_leg = cq.Workplane('XY').rect(5, 0.5)
    print(f"Created pin leg: {pin_leg}")

    # Extrude to 3D for visualization/export
    body_3d = body.extrude(0.1)
    pin_3d = pin_leg.extrude(0.1)

    print(f"  Body 3D volume: {body_3d.val().Volume()}")
    print(f"  Pin 3D volume: {pin_3d.val().Volume()}")

    # Combine into single object
    combined = body_3d.union(pin_3d)
    print(f"Combined shape: {combined}")

    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Cadquery Installation Test")
    print("=" * 60)

    test_cadquery_basic()
    test_cadquery_to_trimesh()
    test_2d_geometry_for_schematic()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
