"""Tests for GLB hierarchy simplification."""

from pygltflib import GLTF2, Node, Scene

from src.core.glb_optimizer import simplify_glb_hierarchy


def test_simplify_glb_hierarchy_collapses_identity_wrapper_chain():
    """Single-child UUID-style wrapper chains should collapse into the named parent."""
    gltf = GLTF2(
        nodes=[
            Node(name="Package", children=[1, 4], rotation=[0.0, 0.0, 0.0, 1.0]),
            Node(name="DesignatorName", children=[2], extras={}),
            Node(name="uuid-node", children=[3], extras={}),
            Node(name="uuid-node_part", mesh=0, extras={}),
            Node(name="PackageValue", mesh=1, extras={}),
        ],
        scenes=[Scene(nodes=[0])],
    )

    original_count, simplified_count = simplify_glb_hierarchy(gltf)

    assert original_count == 5
    assert simplified_count == 3
    assert [node.name for node in gltf.nodes] == [
        "Package",
        "DesignatorName",
        "PackageValue",
    ]
    assert gltf.nodes[1].mesh == 0
    assert gltf.nodes[1].children == []
    assert gltf.scenes[0].nodes == [0]


def test_simplify_glb_hierarchy_keeps_branch_nodes_and_transforms():
    """Branch nodes and non-identity transforms should remain intact."""
    gltf = GLTF2(
        nodes=[
            Node(name="Package", children=[1, 6], rotation=[0.0, 0.0, 0.70710678, 0.70710678]),
            Node(name="BodyLine", children=[2, 4], extras={}),
            Node(name="BodyLine_Top", children=[3], extras={}),
            Node(name="BodyLine_Top_part", mesh=0, extras={}),
            Node(name="BodyLine_Bottom", children=[5], extras={}),
            Node(name="BodyLine_Bottom_part", mesh=1, extras={}),
            Node(name="RotatedWrapper", children=[7], translation=[1.0, 0.0, 0.0], extras={}),
            Node(name="RotatedWrapper_part", mesh=2, extras={}),
        ],
        scenes=[Scene(nodes=[0])],
    )

    original_count, simplified_count = simplify_glb_hierarchy(gltf)

    assert original_count == 8
    assert simplified_count == 6
    assert [node.name for node in gltf.nodes] == [
        "Package",
        "BodyLine",
        "BodyLine_Top",
        "BodyLine_Bottom",
        "RotatedWrapper",
        "RotatedWrapper_part",
    ]
    assert gltf.nodes[1].children == [2, 3]
    assert gltf.nodes[2].mesh == 0
    assert gltf.nodes[3].mesh == 1
    assert gltf.nodes[4].translation == [1.0, 0.0, 0.0]
    assert gltf.nodes[4].children == [5]
