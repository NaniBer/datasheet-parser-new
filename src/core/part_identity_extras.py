"""Write part identity (manufacturer, description, footprint name) into a GLB.

The platform builds its part-properties record from the ``Package`` root node's
extras, so the identity goes there, under the platform's own property names
(``manufacturer``, ``description``, ``footprintName``, ``supplierFootprint``,
``manufacturerPartNumber``) — see ``src/pdf_extractor/part_identity.py``.
"""

from typing import Dict

try:
    from pygltflib import GLTF2
except ImportError:  # pragma: no cover
    GLTF2 = None


def inject_part_identity(glb_path: str, fields: Dict[str, object]) -> bool:
    """Merge *fields* into the extras of the GLB's root ``Package`` node.

    Returns True when the node was found and updated; empty *fields* or a GLB
    without a ``Package`` root leave the file untouched.
    """
    if GLTF2 is None or not fields:
        return False
    gltf = GLTF2().load_binary(glb_path)
    if not gltf.scenes:
        return False
    roots = gltf.scenes[gltf.scene or 0].nodes or []
    for index in roots:
        node = gltf.nodes[index]
        if node.name == "Package":
            merged = dict(node.extras or {})
            merged.update(fields)
            node.extras = merged
            gltf.save_binary(glb_path)
            return True
    return False
