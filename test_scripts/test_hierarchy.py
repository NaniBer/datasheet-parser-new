"""
Build DIP-8 PCB footprint:
1. Generate meshes + materials with trimesh (handles normals, GLB export correctly)
2. Post-process GLB node tree with pygltflib to add proper hierarchy
"""

import trimesh
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io, os, base64


def cylinder(cx, cy, r, h, color, segs=32):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=segs)
    m.apply_translation([cx, cy, 0])
    m.visual.vertex_colors = color
    return m


def box(cx, cy, w, h, zh, color):
    m = trimesh.creation.box(extents=[w, h, zh])
    m.apply_translation([cx, cy, zh / 2])
    m.visual.vertex_colors = color
    return m


def text_quad(cx, cy, text, w, h, font_size=48):
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = ImageFont.load_default()
    img = Image.new("RGBA", (512, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("RGBA", (tw + 16, th + 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((8, 4), text, fill=(255, 255, 255, 255), font=font)

    iw, ih = img.width, img.height
    sx, sy = w / iw, h / ih
    verts = np.array([
        [cx - w/2, cy - h/2, 0], [cx + w/2, cy - h/2, 0],
        [cx + w/2, cy + h/2, 0], [cx - w/2, cy + h/2, 0],
    ], dtype=np.float32)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], dtype=np.float32)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    from trimesh.visual.texture import SimpleMaterial, TextureVisuals
    from PIL import Image as PILImage
    pil_img = PILImage.open(io.BytesIO(png_bytes)).convert("RGBA")
    mat = SimpleMaterial(image=pil_img, diffuse=(1.0, 1.0, 1.0))
    vis = TextureVisuals(uv=uvs, material=mat)

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, visual=vis)
    return mesh


W = [255, 255, 255]
R = [255, 0, 0]
BN = [56, 31, 0]
K = [0, 0, 0]
P = [23, 5, 43]
T = [0, 0, 0, 0]  # transparent


def build(output_path="test_dip8.glb"):
    print("Building DIP-8...")

    bw, bh = 6.35, 9.40
    pitch, row = 2.54, 5.08
    bt, bz = 0.12, 0.015
    pr, hr, sr = 0.625, 0.415, 0.676
    pz, cz = 0.02, 0.2
    mg = 0.25

    left_x, right_x = -row/2, row/2
    start_y = 3 * pitch / 2
    pin_pos = {}
    for i in range(4):
        y = start_y - i * pitch
        pin_pos[i+1] = (left_x, y)
    for i in range(4):
        y = start_y - i * pitch
        pin_pos[8-i] = (right_x, y)

    geo = {}  # name -> (trimesh, geometry_key)

    # Body lines
    for name, cx, cy, w, h in [
        ("fab_top", 0, bh/2, bw, bt),
        ("fab_bottom", 0, -bh/2, bw, bt),
        ("fab_left", -bw/2, 0, bt, bh),
        ("fab_right", bw/2, 0, bt, bh),
    ]:
        geo[name] = box(cx, cy, w, h, bz, W)

    for name, cx, cy in [("silk_top", 0, bh/2), ("silk_bottom", 0, -bh/2)]:
        geo[name] = box(cx, cy, bw, bt, bz, W)

    for name, cx, cy, w, h in [
        ("crtyd_top", 0, (bh+2*mg)/2, bw+2*mg, bt),
        ("crtyd_bottom", 0, -(bh+2*mg)/2, bw+2*mg, bt),
        ("crtyd_left", -(bw+2*mg)/2, 0, bt, bh+2*mg),
        ("crtyd_right", (bw+2*mg)/2, 0, bt, bh+2*mg),
    ]:
        geo[name] = box(cx, cy, w, h, bz, P)

    # Pins
    for pn in range(1, 9):
        x, y = pin_pos[pn]
        pk = str(pn)
        geo[f"{pk}_sm"] = cylinder(x, y, sr, pz, BN)
        geo[f"{pk}_cp"] = cylinder(x, y, pr, pz, R)
        geo[f"{pk}_hole"] = cylinder(x, y, hr, cz, K)
        geo[f"{pk}_cyl"] = cylinder(x, y, hr, cz, R)
        bp = cylinder(x, y, pr, pz, R)
        bp.apply_translation([0, 0, -cz])
        geo[f"{pk}_bp"] = bp
        geo[f"{pk}_txt"] = text_quad(x, y - 0.6, str(pn), 0.5, 0.18, font_size=36)

    # FirstPinMarker
    p1x, p1y = pin_pos[1]
    geo["silk_pm"] = cylinder(p1x - 0.8, p1y + 0.8, 0.1, 0.15, W, segs=12)
    geo["fab_pm"] = cylinder(p1x - 0.8, p1y + 0.8, 0.1, 0.15, W, segs=12)

    # DesignatorName
    geo["des_body"] = text_quad(0, bh/2 + 1.8, "U1", 1.2, 0.35)
    geo["des_bbox"] = box(0, bh/2 + 1.8, 1.6, 0.55, 0.01, T)

    # PackageValue
    geo["pv_body"] = text_quad(0, bh/2 + 3.0, "DIP-8", 1.0, 0.3, font_size=42)
    geo["pv_bbox"] = box(0, bh/2 + 3.0, 1.4, 0.5, 0.01, T)

    # Build flat scene (trimesh export - correct normals, materials, binary)
    scene = trimesh.Scene()
    for name, mesh in geo.items():
        scene.add_geometry(mesh, node_name=name)

    # Export flat GLB
    scene.export(output_path)
    flat_size = os.path.getsize(output_path)

    # Now restructure hierarchy with pygltflib
    from pygltflib import GLTF2, Scene as GLTFScene

    gltf = GLTF2().load(output_path)
    gltf.scenes = [GLTFScene()]

    # Build node name -> index map
    name_to_idx = {}
    for i, n in enumerate(gltf.nodes):
        if n.name:
            name_to_idx[n.name] = i

    # Define hierarchy
    hierarchy = {
        "world": ["Package"],
        "Package": ["DesignatorName", "PackageValue", "FirstPinMarker", "Legs", "Body"],
        "DesignatorName": ["des_body", "des_bbox"],
        "PackageValue": ["pv_body", "pv_bbox"],
        "FirstPinMarker": ["silk_pm", "fab_pm"],
        "Body": ["fab_layer", "silk_layer", "crtyd_layer"],
        "fab_layer": ["fab_top", "fab_bottom", "fab_left", "fab_right"],
        "silk_layer": ["silk_top", "silk_bottom"],
        "crtyd_layer": ["crtyd_top", "crtyd_bottom", "crtyd_left", "crtyd_right"],
        "Legs": ["1", "2", "3", "4", "5", "6", "7", "8"],
    }

    # Add pin hierarchy
    for pn in range(1, 9):
        pk = str(pn)
        hierarchy[pk] = [f"{pk}_sm", f"{pk}_cp", f"{pk}_hole", f"{pk}_cyl", f"{pk}_bp", f"{pk}_txt"]

    # Create wrapper nodes for hierarchy parents that aren't mesh nodes
    wrapper_names = ["Package", "DesignatorName", "PackageValue", "FirstPinMarker",
                     "Body", "fab_layer", "silk_layer", "crtyd_layer", "Legs", "1", "2", "3", "4", "5", "6", "7", "8"]

    # Create wrapper nodes
    import copy
    wrapper_nodes = []
    for wname in wrapper_names:
        wnodes = [n for n in gltf.nodes if n.name == wname]
        if wnodes:
            wrapper_nodes.append(wnodes[0])
        else:
            from pygltflib import Node as GLTFNode
            n = GLTFNode(name=wname)
            wrapper_nodes.append(n)
            gltf.nodes.append(n)

    # Build final flat node list with correct children
    all_node_names = ["world"] + wrapper_names + list(name_to_idx.keys())

    # Create world node
    world_node = None
    for n in gltf.nodes:
        if n.name == "world":
            world_node = n
            break

    # Set children for each parent
    node_map = {}
    for i, n in enumerate(gltf.nodes):
        node_map[n.name] = i

    for parent_name, child_names in hierarchy.items():
        if parent_name in node_map:
            children = [node_map[cn] for cn in child_names if cn in node_map]
            gltf.nodes[node_map[parent_name]].children = children

    # Scene root = world
    gltf.scenes[0].nodes = [node_map["world"]]

    # Clean up: remove mesh references from wrapper nodes that shouldn't have them
    for wname in wrapper_names:
        idx = node_map.get(wname)
        if idx is not None:
            gltf.nodes[idx].mesh = None

    gltf.save(output_path)
    sz = os.path.getsize(output_path)

    def pt(g, idx, indent=0):
        n = g.nodes[idx]
        m = f" [mesh]" if n.mesh is not None else ""
        print("  " * indent + f"├── {n.name}{m}")
        if n.children:
            for c in n.children:
                pt(g, c, indent + 1)

    print(f"\nExported: {output_path} ({sz/1024:.1f} KB)")
    print(f"Flat size: {flat_size/1024:.1f} KB")
    print(f"\nHierarchy:")
    root = gltf.scenes[0].nodes[0]
    pt(gltf, root)
    print(f"\nNodes: {len(gltf.nodes)}, Meshes: {len(gltf.meshes)}")

    return True


if __name__ == "__main__":
    build()
