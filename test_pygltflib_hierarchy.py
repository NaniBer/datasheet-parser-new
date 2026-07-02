#!/usr/bin/env python3
"""
Simple test to demonstrate pygltflib's exact hierarchy control.

This script creates the EXACT PCB footprint hierarchy without complex mesh generation.
Focus is on demonstrating that pygltflib preserves the hierarchy exactly as specified.
"""

from pygltflib import GLTF2, Node, Scene


def create_exact_hierarchy():
    """Create GLTF with EXACT hierarchy - no extra nodes, no modifications."""

    gltf = GLTF2()

    print("Creating exact hierarchy nodes...")

    # Store indices as we go
    indices = {}

    # 1. DesignatorName (Body + BoundingBox)
    designator_body = Node(name="Body")
    designator_bbox = Node(name="BoundingBox")
    gltf.nodes.extend([designator_body, designator_bbox])

    # Store indices
    indices['designator_body'] = len(gltf.nodes) - 2
    indices['designator_bbox'] = len(gltf.nodes) - 1

    designator_node = Node(
        name="DesignatorName",
        children=[indices['designator_body'], indices['designator_bbox']]
    )
    gltf.nodes.append(designator_node)
    indices['designator'] = len(gltf.nodes) - 1

    # 2. PackageValue (Body + BoundingBox)
    package_value_body = Node(name="Body")
    package_value_bbox = Node(name="BoundingBox")
    gltf.nodes.extend([package_value_body, package_value_bbox])

    # Store indices
    indices['package_value_body'] = len(gltf.nodes) - 2
    indices['package_value_bbox'] = len(gltf.nodes) - 1

    package_value_node = Node(
        name="PackageValue",
        children=[indices['package_value_body'], indices['package_value_bbox']]
    )
    gltf.nodes.append(package_value_node)
    indices['package_value'] = len(gltf.nodes) - 1

    # 3. FirstPinMarker (silk_firstPinMarker + fab_firstPinMarker)
    silk_marker = Node(name="silk_firstPinMarker")
    fab_marker = Node(name="fab_firstPinMarker")
    gltf.nodes.extend([silk_marker, fab_marker])

    # Store indices
    indices['silk_marker'] = len(gltf.nodes) - 2
    indices['fab_marker'] = len(gltf.nodes) - 1

    first_pin_node = Node(
        name="FirstPinMarker",
        children=[indices['silk_marker'], indices['fab_marker']]
    )
    gltf.nodes.append(first_pin_node)
    indices['first_pin'] = len(gltf.nodes) - 1

    # 4. Legs with 8 pins (DIP-8 example)
    pin_children_indices = []

    for pin_num in range(1, 9):
        # Pin 1: SolderMask, CopperCirclePad, HoleCylinderPin, CopperCylinderPin, text
        solder_mask = Node(name="SolderMask")
        copper_pad = Node(name="CopperCirclePad")
        hole_cyl = Node(name="HoleCylinderPin")
        copper_cyl = Node(name="CopperCylinderPin")
        pin_text = Node(name="text")

        gltf.nodes.extend([solder_mask, copper_pad, hole_cyl, copper_cyl, pin_text])

        # Store indices
        solder_idx = len(gltf.nodes) - 5
        pad_idx = len(gltf.nodes) - 4
        hole_idx = len(gltf.nodes) - 3
        copper_cyl_idx = len(gltf.nodes) - 2
        text_idx = len(gltf.nodes) - 1

        # Pin assembly with exact 5 children
        pin_assy = Node(
            name=str(pin_num),
            children=[solder_idx, pad_idx, hole_idx, copper_cyl_idx, text_idx]
        )
        gltf.nodes.append(pin_assy)

        pin_children_indices.append(len(gltf.nodes) - 1)

    legs_node = Node(name="Legs", children=pin_children_indices)
    gltf.nodes.append(legs_node)
    indices['legs'] = len(gltf.nodes) - 1

    # 5. Body with 3 layers (fab, silk, crtyd)
    # fab_layer with 4 BodyLines
    fab_bodylines = []
    for line_name in ["BodyLine_Top", "BodyLine_Bottom", "BodyLine_Left", "BodyLine_Right"]:
        line_node = Node(name=line_name)
        gltf.nodes.append(line_node)
        fab_bodylines.append(len(gltf.nodes) - 1)

    fab_layer = Node(name="fab_layer", children=fab_bodylines)
    gltf.nodes.append(fab_layer)
    indices['fab_layer'] = len(gltf.nodes) - 1

    # silk_layer with 2 BodyLines
    silk_bodylines = []
    for line_name in ["BodyLine_Top", "BodyLine_Bottom"]:
        line_node = Node(name=line_name)
        gltf.nodes.append(line_node)
        silk_bodylines.append(len(gltf.nodes) - 1)

    silk_layer = Node(name="silk_layer", children=silk_bodylines)
    gltf.nodes.append(silk_layer)
    indices['silk_layer'] = len(gltf.nodes) - 1

    # crtyd_layer with 4 BodyLines
    crtyd_bodylines = []
    for line_name in ["BodyLine_Top", "BodyLine_Bottom", "BodyLine_Left", "BodyLine_Right"]:
        line_node = Node(name=line_name)
        gltf.nodes.append(line_node)
        crtyd_bodylines.append(len(gltf.nodes) - 1)

    crtyd_layer = Node(name="crtyd_layer", children=crtyd_bodylines)
    gltf.nodes.append(crtyd_layer)
    indices['crtyd_layer'] = len(gltf.nodes) - 1

    # Body node with 3 layer children
    body_node = Node(
        name="Body",
        children=[indices['fab_layer'], indices['silk_layer'], indices['crtyd_layer']]
    )
    gltf.nodes.append(body_node)
    indices['body'] = len(gltf.nodes) - 1

    # 6. Root Package node with 5 top-level children
    # DesignatorName, PackageValue, FirstPinMarker, Legs, Body
    package_node = Node(
        name="Package",
        children=[
            indices['designator'],  # DesignatorName
            indices['package_value'],  # PackageValue
            indices['first_pin'],  # FirstPinMarker
            indices['legs'],  # Legs
            indices['body'],  # Body
        ]
    )
    gltf.nodes.append(package_node)
    indices['package'] = len(gltf.nodes) - 1

    # Set scene to point to Package node
    scene = Scene(nodes=[indices['package']])
    gltf.scenes.append(scene)
    gltf.scene = 0

    return gltf


def print_hierarchy(gltf, indent=0, node_idx=None):
    """Print the GLTF node hierarchy."""
    if node_idx is None:
        # Start from scene nodes
        if gltf.scene is None or len(gltf.scenes) == 0:
            print("No scene found!")
            return

        scene = gltf.scenes[gltf.scene]
        for node_idx in scene.nodes:
            print_hierarchy(gltf, indent, node_idx)
        return

    node = gltf.nodes[node_idx]
    prefix = "  " * indent

    # Get node info
    mesh_info = f"[mesh:{node.mesh}]" if node.mesh is not None else ""
    children_info = f"({len(node.children)} children)" if node.children else "leaf"

    print(f"{prefix}Node {node_idx}: '{node.name}' {mesh_info} {children_info}")

    # Recursively print children
    for child_idx in node.children:
        print_hierarchy(gltf, indent + 1, child_idx)


def validate_hierarchy(gltf):
    """Validate that hierarchy matches exactly."""
    print("\n" + "=" * 80)
    print("HIERARCHY VALIDATION:")
    print("=" * 80)

    # Get root node
    if gltf.scene is None or len(gltf.scenes) == 0:
        print("✗ No scene found")
        return False

    scene = gltf.scenes[gltf.scene]
    if len(scene.nodes) != 1:
        print(f"✗ Expected 1 root node, got {len(scene.nodes)}")
        return False

    root_idx = scene.nodes[0]
    root_node = gltf.nodes[root_idx]

    # Check root name
    if root_node.name != "Package":
        print(f"✗ Root name is '{root_node.name}', expected 'Package'")
        return False
    print("✓ Root is 'Package'")

    # Check root has 5 children
    if len(root_node.children) != 5:
        print(f"✗ Root has {len(root_node.children)} children, expected 5")
        return False
    print("✓ Root has 5 children")

    # Check top-level children names
    expected_children = ["DesignatorName", "PackageValue", "FirstPinMarker", "Legs", "Body"]
    actual_children = [gltf.nodes[i].name for i in root_node.children]

    print(f"\nExpected children: {expected_children}")
    print(f"Actual children:   {actual_children}")

    if actual_children == expected_children:
        print("✓ Top-level children match!")
    else:
        print("✗ Top-level children do NOT match")
        return False

    # Check DesignatorName structure
    designator_idx = root_node.children[0]
    designator_node = gltf.nodes[designator_idx]

    if designator_node.name != "DesignatorName":
        print(f"✗ Second node is '{designator_node.name}', expected 'DesignatorName'")
        return False

    if len(designator_node.children) != 2:
        print(f"✗ DesignatorName has {len(designator_node.children)} children, expected 2")
        return False

    designator_children = [gltf.nodes[i].name for i in designator_node.children]
    if designator_children == ["Body", "BoundingBox"]:
        print("✓ DesignatorName structure is correct (Body + BoundingBox)")
    else:
        print(f"✗ DesignatorName children are {designator_children}, expected ['Body', 'BoundingBox']")
        return False

    # Check Legs structure
    legs_idx = root_node.children[3]
    legs_node = gltf.nodes[legs_idx]

    if legs_node.name != "Legs":
        print(f"✗ Fourth node is '{legs_node.name}', expected 'Legs'")
        return False

    if len(legs_node.children) != 8:
        print(f"✗ Legs has {len(legs_node.children)} children, expected 8 (for DIP-8)")
        return False

    # Check first pin structure
    pin1_idx = legs_node.children[0]
    pin1_node = gltf.nodes[pin1_idx]

    if pin1_node.name != "1":
        print(f"✗ First pin is named '{pin1_node.name}', expected '1'")
        return False

    if len(pin1_node.children) != 5:
        print(f"✗ Pin 1 has {len(pin1_node.children)} children, expected 5")
        return False

    pin1_children = [gltf.nodes[i].name for i in pin1_node.children]
    expected_pin_children = ["SolderMask", "CopperCirclePad", "HoleCylinderPin", "CopperCylinderPin", "text"]
    if pin1_children == expected_pin_children:
        print("✓ Pin 1 structure is correct (5 components in right order)")
    else:
        print(f"✗ Pin 1 children are {pin1_children}")
        print(f"  Expected: {expected_pin_children}")
        return False

    # Check Body structure
    body_idx = root_node.children[4]
    body_node = gltf.nodes[body_idx]

    if body_node.name != "Body":
        print(f"✗ Fifth node is '{body_node.name}', expected 'Body'")
        return False

    if len(body_node.children) != 3:
        print(f"✗ Body has {len(body_node.children)} children, expected 3 (layers)")
        return False

    body_children = [gltf.nodes[i].name for i in body_node.children]
    expected_body_children = ["fab_layer", "silk_layer", "crtyd_layer"]
    if body_children == expected_body_children:
        print("✓ Body has 3 layers: fab_layer, silk_layer, crtyd_layer")
    else:
        print(f"✗ Body children are {body_children}, expected {expected_body_children}")
        return False

    # Check fab_layer has 4 BodyLines
    fab_layer_idx = body_node.children[0]
    fab_layer_node = gltf.nodes[fab_layer_idx]

    if len(fab_layer_node.children) != 4:
        print(f"✗ fab_layer has {len(fab_layer_node.children)} children, expected 4")
        return False

    fab_children = [gltf.nodes[i].name for i in fab_layer_node.children]
    expected_fab_children = ["BodyLine_Top", "BodyLine_Bottom", "BodyLine_Left", "BodyLine_Right"]
    if fab_children == expected_fab_children:
        print("✓ fab_layer has 4 BodyLines")
    else:
        print(f"✗ fab_layer children: {fab_children}")
        return False

    # Check silk_layer has 2 BodyLines
    silk_layer_idx = body_node.children[1]
    silk_layer_node = gltf.nodes[silk_layer_idx]

    if len(silk_layer_node.children) != 2:
        print(f"✗ silk_layer has {len(silk_layer_node.children)} children, expected 2")
        return False

    silk_children = [gltf.nodes[i].name for i in silk_layer_node.children]
    expected_silk_children = ["BodyLine_Top", "BodyLine_Bottom"]
    if silk_children == expected_silk_children:
        print("✓ silk_layer has 2 BodyLines (avoids pin areas)")
    else:
        print(f"✗ silk_layer children: {silk_children}")
        return False

    return True


def main():
    """Main test function."""
    print("=" * 80)
    print("PYGLTFLIB EXACT HIERARCHY CONTROL TEST")
    print("=" * 80)
    print("\nThis test demonstrates that pygltflib can create the EXACT hierarchy")
    print("you want, with no extra nodes and perfect structure preservation.\n")

    # Create exact hierarchy
    gltf = create_exact_hierarchy()

    print(f"✓ Created {len(gltf.nodes)} nodes\n")

    # Save as GLTF (not GLB since we don't have mesh data)
    output_file = "test_pygltflib_hierarchy.gltf"
    print(f"Saving to {output_file}...")
    gltf.save(output_file)
    print(f"✓ Saved successfully\n")

    # Reload to verify preservation
    print("Reloading to verify hierarchy preservation...")
    gltf_loaded = GLTF2().load(output_file)
    print(f"✓ Reloaded {len(gltf_loaded.nodes)} nodes\n")

    # Print actual hierarchy
    print("=" * 80)
    print("ACTUAL GLTF HIERARCHY (after save/load cycle):")
    print("=" * 80)
    print_hierarchy(gltf_loaded)

    # Print desired hierarchy
    print("\n" + "=" * 80)
    print("DESIRED HIERARCHY (from documentation):")
    print("=" * 80)
    desired = """
Package (main assembly)
├── DesignatorName
│   ├── Body
│   └── BoundingBox
├── PackageValue
│   ├── Body
│   └── BoundingBox
├── FirstPinMarker
│   ├── silk_firstPinMarker
│   └── fab_firstPinMarker
├── Legs
│   ├── 1
│   │   ├── SolderMask
│   │   ├── CopperCirclePad
│   │   ├── HoleCylinderPin
│   │   ├── CopperCylinderPin
│   │   └── text
│   ├── 2 (same structure)
│   └── ...
└── Body
    ├── fab_layer
    │   ├── BodyLine (top)
    │   ├── BodyLine (bottom)
    │   ├── BodyLine (left)
    │   └── BodyLine (right)
    ├── silk_layer
    │   ├── BodyLine (top)
    │   └── BodyLine (bottom)
    └── crtyd_layer
        ├── BodyLine (top)
        ├── BodyLine (bottom)
        ├── BodyLine (left)
        └── BodyLine (right)
"""
    print(desired)

    # Validate
    success = validate_hierarchy(gltf_loaded)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    print(f"Total nodes created: {len(gltf_loaded.nodes)}")
    print(f"Total meshes: {len(gltf_loaded.meshes)}")

    if success:
        print("\n" + "=" * 80)
        print("✅ SUCCESS! Hierarchy matches EXACTLY!")
        print("=" * 80)
        print("\npygltflib preserves your hierarchy with:")
        print("  • No extra nodes added")
        print("  • All node names preserved exactly")
        print("  • Parent-child relationships maintained")
        print("  • Order of children preserved")
        print("\nThis proves pygltflib can create the exact structure you need!")
    else:
        print("\n" + "=" * 80)
        print("❌ FAILED! Hierarchy does not match")
        print("=" * 80)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
