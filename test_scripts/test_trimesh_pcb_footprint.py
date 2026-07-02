"""
Build DIP-8 PCB footprint with full hierarchy (PCB_FOOTPRINT_HIERARCHY.md spec).
Uses trimesh for mesh generation + pygltflib for hierarchical node structure.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io, os, base64

# =============================================================================
# Mesh generators
# =============================================================================

def compute_normals(verts, faces):
    """Compute vertex normals for a mesh."""
    norms = np.zeros((len(verts), 3), dtype=np.float32)
    for f in faces:
        v0, v1, v2 = verts[f[0]], verts[f[1]], verts[f[2]]
        n = np.cross(v1 - v0, v2 - v0)
        nlen = np.linalg.norm(n)
        if nlen > 0:
            n /= nlen
        for idx in f:
            norms[idx] += n
    for i in range(len(norms)):
        nlen = np.linalg.norm(norms[i])
        if nlen > 0:
            norms[i] /= nlen
    return norms


def cylinder_verts_faces_normals(cx, cy, r, h, segs=24):
    """Return (vertices, normals, faces) for a cylinder at (cx,cy) from z=0 to z=h."""
    angles = np.linspace(0, 2*np.pi, segs, endpoint=False)
    bot = np.array([[cx + r*np.cos(a), cy + r*np.sin(a), 0] for a in angles], dtype=np.float32)
    top = np.array([[cx + r*np.cos(a), cy + r*np.sin(a), h] for a in angles], dtype=np.float32)
    verts = np.vstack([bot, top, [cx, cy, 0], [cx, cy, h]])
    ctr_bot = 2*segs
    ctr_top = 2*segs + 1

    faces = []
    for i in range(segs):
        j = (i + 1) % segs
        faces.append([i, j, j + segs])
        faces.append([i, j + segs, i + segs])
        faces.append([ctr_bot, j, i])
        faces.append([ctr_top, i + segs, j + segs])

    faces = np.array(faces, dtype=np.int32)
    norms = compute_normals(verts, faces)
    return verts, norms, faces


def box_verts_faces_normals(cx, cy, w, h, zh):
    """Return (vertices, normals, faces) for a box centered at (cx,cy), height zh."""
    hw, hh = w/2, h/2
    verts = np.array([
        [cx-hw, cy-hh, 0], [cx+hw, cy-hh, 0], [cx+hw, cy+hh, 0], [cx-hw, cy+hh, 0],
        [cx-hw, cy-hh, zh], [cx+hw, cy-hh, zh], [cx+hw, cy+hh, zh], [cx-hw, cy+hh, zh],
    ], dtype=np.float32)
    faces = np.array([
        [0,1,2],[0,2,3],[4,6,5],[4,7,6],
        [0,4,5],[0,5,1],[3,2,6],[3,6,7],
        [0,3,7],[0,7,4],[1,5,6],[1,6,2],
    ], dtype=np.int32)
    norms = compute_normals(verts, faces)
    return verts, norms, faces


def text_quad_verts_uvs(cx, cy, w, h):
    """Return vertices, faces, UVs for a textured quad."""
    verts = np.array([
        [cx-w/2, cy-h/2, 0], [cx+w/2, cy-h/2, 0],
        [cx+w/2, cy+h/2, 0], [cx-w/2, cy+h/2, 0],
    ], dtype=np.float32)
    faces = np.array([[0,1,2],[0,2,3]], dtype=np.int32)
    uvs = np.array([[0,1],[1,1],[1,0],[0,0]], dtype=np.float32)
    return verts, faces, uvs


def render_text_image(text, font_size=48):
    """Render text to RGBA PIL image, return (png_bytes, width, height)."""
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = ImageFont.load_default()
    img = Image.new("RGBA", (512, 128), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    img = Image.new("RGBA", (tw+16, th+8), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    draw.text((8,4), text, fill=(255,255,255,255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), img.width, img.height


# =============================================================================
# GLB builder
# =============================================================================

from pygltflib import GLTF2, Buffer, BufferView, Accessor, Mesh, Primitive, Node, Scene
from pygltflib import Material, PbrMetallicRoughness, Texture, TextureInfo, Sampler, Image as GLTFImage


class GLBHierarchyBuilder:
    """Build a hierarchical GLB from named meshes."""

    def __init__(self):
        self.gltf = GLTF2()
        self.gltf.asset = {"version": "2.0", "generator": "pcb_footprint_builder"}

        self.mesh_defs = []  # list of dicts
        self.materials = []
        self.textures = []
        self.samplers = []
        self.images = []
        self.nodes = []

        self.mat_cache = {}
        self.img_cache = {}

    def _get_or_create_mat(self, color):
        key = tuple(round(c, 6) for c in (color[:3] if len(color) >= 3 else color))
        if key in self.mat_cache:
            return self.mat_cache[key]
        idx = len(self.materials)
        rgba = color if len(color) == 4 else list(color) + [1.0]
        self.materials.append(Material(
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorFactor=rgba, metallicFactor=0.0, roughnessFactor=0.5,
            )
        ))
        self.mat_cache[key] = idx
        return idx

    def _get_or_create_tex(self, text, font_size=48):
        k = (text, font_size)
        if k in self.img_cache:
            return self.img_cache[k]
        png_bytes, w, h = render_text_image(text, font_size)
        b64 = base64.b64encode(png_bytes).decode()
        img_idx = len(self.images)
        self.images.append(GLTFImage(uri=f"data:image/png;base64,{b64}"))
        sampler_idx = len(self.samplers)
        self.samplers.append(Sampler(magFilter=9729, minFilter=9729, wrapS=10497, wrapT=10497))
        tex_idx = len(self.textures)
        self.textures.append(Texture(sampler=sampler_idx, source=img_idx))
        r = (tex_idx, w, h)
        self.img_cache[k] = r
        return r

    def add_solid(self, verts, norms, faces, color, name=""):
        idx = len(self.mesh_defs)
        self.mesh_defs.append({
            "verts": verts, "norms": norms, "faces": faces,
            "mat": self._get_or_create_mat(color),
            "tex": None, "uvs": None, "name": name,
        })
        return idx

    def add_text(self, text, cx, cy, w, h, font_size=48, name=""):
        tex_idx, tw, th = self._get_or_create_tex(text, font_size)
        verts, faces, uvs = text_quad_verts_uvs(cx, cy, w, h)
        norms = np.zeros((len(verts), 3), dtype=np.float32)
        norms[:, 2] = 1.0
        idx = len(self.mesh_defs)
        self.mesh_defs.append({
            "verts": verts, "norms": norms, "faces": faces,
            "mat": self._get_or_create_mat([1,1,1,1]),
            "tex": tex_idx, "uvs": uvs, "name": name,
        })
        return idx

    def add_node(self, name, mesh_idx=None, children=None):
        idx = len(self.nodes)
        n = Node(name=name)
        if mesh_idx is not None:
            n.mesh = mesh_idx
        if children:
            n.children = children
        self.nodes.append(n)
        if name == "world":
            self._root_idx = idx
        return idx

    def export(self, path):
        # Build binary blob: interleave verts + normals, then indices, then UVs
        stride = 24  # 3 floats position + 3 floats normal = 24 bytes
        chunks = []
        byte_offset = 0
        positions = []
        for md in self.mesh_defs:
            positions.append(byte_offset)
            verts = md["verts"]
            norms = md["norms"]
            interleaved = np.empty((len(verts), 6), dtype=np.float32)
            interleaved[:, :3] = verts
            interleaved[:, 3:6] = norms
            data = interleaved.tobytes()
            chunks.append(data)
            byte_offset += len(data)

        idx_positions = []
        for md in self.mesh_defs:
            idx_positions.append(byte_offset)
            data = md["faces"].tobytes()
            chunks.append(data)
            byte_offset += len(data)

        uv_positions = []
        for md in self.mesh_defs:
            if md["tex"] is not None and md["uvs"] is not None:
                uv_positions.append(byte_offset)
                data = md["uvs"].tobytes()
                chunks.append(data)
                byte_offset += len(data)
            else:
                uv_positions.append(-1)

        binary_blob = b"".join(chunks)

        # Buffer
        buf = Buffer(byteLength=len(binary_blob))
        self.gltf.buffers = [buf]

        # BufferViews and Accessors
        bvs = []
        accs = []
        for i, md in enumerate(self.mesh_defs):
            v = md["verts"]
            f = md["faces"]

            # Position+Normal interleaved BV + Acc
            bv = BufferView(buffer=0, byteOffset=positions[i],
                          byteLength=len(v) * stride,
                          target=34962, byteStride=stride)
            bvs.append(bv)
            accs.append(Accessor(
                bufferView=len(bvs)-1, componentType=5126, count=len(v),
                type="VEC3", byteOffset=0,
                max=v.max(axis=0).tolist(), min=v.min(axis=0).tolist(),
            ))

            # Normal accessor (same BV, offset 12 bytes)
            accs.append(Accessor(
                bufferView=len(bvs)-1, componentType=5126, count=len(v),
                type="VEC3", byteOffset=12,
            ))

            # Index BV + Acc
            ib = BufferView(buffer=0, byteOffset=idx_positions[i],
                          byteLength=len(f) * 12, target=34963)
            bvs.append(ib)
            accs.append(Accessor(
                bufferView=len(bvs)-1, componentType=5125, count=len(f) * 3,
                type="SCALAR",
            ))

        # UV BVs + Accs
        for i, md in enumerate(self.mesh_defs):
            if md["tex"] is not None and md["uvs"] is not None:
                uvs = md["uvs"]
                bv = BufferView(buffer=0, byteOffset=uv_positions[i],
                              byteLength=len(uvs) * 8,
                              target=34962, byteStride=8)
                bvs.append(bv)
                accs.append(Accessor(
                    bufferView=len(bvs)-1, componentType=5126, count=len(uvs),
                    type="VEC2",
                ))

        self.gltf.bufferViews = bvs
        self.gltf.accessors = accs

        # Build meshes
        meshes = []
        uv_acc_offset = len(self.mesh_defs) * 3
        uv_used = 0
        for i, md in enumerate(self.mesh_defs):
            pos_acc = i * 3
            norm_acc = i * 3 + 1
            idx_acc = i * 3 + 2
            prim = Primitive(
                attributes={"POSITION": pos_acc, "NORMAL": norm_acc},
                indices=idx_acc,
                material=md["mat"],
            )
            if md["tex"] is not None:
                prim.attributes["TEXCOORD_0"] = uv_acc_offset + uv_used
                uv_used += 1
            meshes.append(Mesh(primitives=[prim], name=md.get("name", f"m{i}")))
        self.gltf.meshes = meshes

        self.gltf.materials = self.materials
        self.gltf.textures = self.textures
        self.gltf.samplers = self.samplers
        self.gltf.images = self.images
        self.gltf.nodes = self.nodes
        self.gltf.scenes = [Scene(nodes=[self._root_idx])]

        self.gltf.set_binary_blob(binary_blob)
        self.gltf.save(path)

        sz = os.path.getsize(path)
        print(f"Exported: {path} ({sz/1024:.1f} KB)")
        return sz


# =============================================================================
# Main build
# =============================================================================

def build_dip8(output_path="test_dip8_hierarchy.glb"):
    print("Building DIP-8 with full hierarchy\n")

    body_w, body_h = 6.35, 9.40
    pitch, row = 2.54, 5.08
    bt, bh = 0.12, 0.015
    pr, hr, sr = 0.625, 0.415, 0.676
    ph, ch = 0.02, 0.2
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

    C = {
        "w": [1,1,1,1], "r": [1,0,0,1],
        "bn": [0.22,0.12,0,1], "k": [0,0,0,1],
        "p": [0.09,0.02,0.17,1],
        "t": [0,0,0,0],
    }

    b = GLBHierarchyBuilder()
    m = {}  # mesh index lookup

    # Body outlines
    for side, cx, cy, wd, hd in [
        ("fab_top", 0, body_h/2, body_w, bt),
        ("fab_bottom", 0, -body_h/2, body_w, bt),
        ("fab_left", -body_w/2, 0, bt, body_h),
        ("fab_right", body_w/2, 0, bt, body_h),
    ]:
        v, n, f = box_verts_faces_normals(cx, cy, wd, hd, bh)
        m[side] = b.add_solid(v, n, f, C["w"], side)

    for side, cx, cy in [("silk_top", 0, body_h/2), ("silk_bottom", 0, -body_h/2)]:
        v, n, f = box_verts_faces_normals(cx, cy, body_w, bt, bh)
        m[side] = b.add_solid(v, n, f, C["w"], side)

    for side, cx, cy, wd, hd in [
        ("crtyd_top", 0, (body_h+2*mg)/2, body_w+2*mg, bt),
        ("crtyd_bottom", 0, -(body_h+2*mg)/2, body_w+2*mg, bt),
        ("crtyd_left", -(body_w+2*mg)/2, 0, bt, body_h+2*mg),
        ("crtyd_right", (body_w+2*mg)/2, 0, bt, body_h+2*mg),
    ]:
        v, n, f = box_verts_faces_normals(cx, cy, wd, hd, bh)
        m[side] = b.add_solid(v, n, f, C["p"], side)

    # Pins
    for pn in range(1, 9):
        x, y = pin_pos[pn]
        pk = str(pn)

        v, n, f = cylinder_verts_faces_normals(x, y, 0.676, ph)
        m[f"{pk}_sm"] = b.add_solid(v, n, f, C["bn"], f"{pk}_sm")

        v, n, f = cylinder_verts_faces_normals(x, y, 0.625, ph)
        m[f"{pk}_cp"] = b.add_solid(v, n, f, C["r"], f"{pk}_cp")

        v, n, f = cylinder_verts_faces_normals(x, y, 0.415, ch)
        m[f"{pk}_hole"] = b.add_solid(v, n, f, C["k"], f"{pk}_hole")

        v, n, f = cylinder_verts_faces_normals(x, y, 0.415, ch)
        m[f"{pk}_cyl"] = b.add_solid(v, n, f, C["r"], f"{pk}_cyl")

        v, n, f = cylinder_verts_faces_normals(x, y, 0.625, ph)
        v[:, 2] -= ch
        m[f"{pk}_bp"] = b.add_solid(v, n, f, C["r"], f"{pk}_bp")

        m[f"{pk}_txt"] = b.add_text(str(pn), x, y-0.6, 0.5, 0.18, font_size=36, name=f"{pk}_txt")

    # FirstPinMarker
    p1x, p1y = pin_pos[1]
    v, n, f = cylinder_verts_faces_normals(p1x-0.8, p1y+0.8, 0.1, 0.15, segs=12)
    m["silk_pm"] = b.add_solid(v, n, f, C["w"], "silk_pm")
    v, n, f = cylinder_verts_faces_normals(p1x-0.8, p1y+0.8, 0.1, 0.15, segs=12)
    m["fab_pm"] = b.add_solid(v, n, f, C["w"], "fab_pm")

    # DesignatorName
    m["des_body"] = b.add_text("U1", 0, body_h/2+1.8, 1.2, 0.35, name="des_body")
    v, n, f = box_verts_faces_normals(0, body_h/2+1.8, 1.6, 0.55, 0.01)
    m["des_bbox"] = b.add_solid(v, n, f, C["t"], "des_bbox")

    # PackageValue
    m["pv_body"] = b.add_text("DIP-8", 0, body_h/2+3.0, 1.0, 0.3, font_size=42, name="pv_body")
    v, n, f = box_verts_faces_normals(0, body_h/2+3.0, 1.4, 0.5, 0.01)
    m["pv_bbox"] = b.add_solid(v, n, f, C["t"], "pv_bbox")

    # Build hierarchy
    def N(name, mesh_idx=None, children=None):
        return b.add_node(name, mesh_idx, children)

    def P(name, child_names):
        indices = []
        for cn in child_names:
            if cn in node_map:
                indices.append(node_map[cn])
            else:
                idx = N(cn, mesh_idx=m[cn])
                node_map[cn] = idx
                indices.append(idx)
        node_map[name] = N(name, children=indices)
        return node_map[name]

    node_map = {}

    # Body
    node_map["fab"] = P("fab_layer", ["fab_top","fab_bottom","fab_left","fab_right"])
    node_map["silk"] = P("silk_layer", ["silk_top","silk_bottom"])
    node_map["crtyd"] = P("crtyd_layer", ["crtyd_top","crtyd_bottom","crtyd_left","crtyd_right"])
    node_map["body"] = N("Body", children=[node_map["fab"], node_map["silk"], node_map["crtyd"]])

    # DesignatorName / PackageValue
    P("DesignatorName", ["des_body","des_bbox"])
    P("PackageValue", ["pv_body","pv_bbox"])

    # FirstPinMarker
    node_map["fpm"] = P("FirstPinMarker", ["silk_pm","fab_pm"])

    # Legs
    pin_nodes = []
    for pn in range(1, 9):
        pk = str(pn)
        childs = [f"{pk}_sm", f"{pk}_cp", f"{pk}_hole", f"{pk}_cyl", f"{pk}_bp", f"{pk}_txt"]
        pi = P(pk, childs)
        pin_nodes.append(pi)
    legs_idx = N("Legs", children=pin_nodes)

    # Package root
    pkg_idx = N("Package", children=[
        node_map["DesignatorName"], node_map["PackageValue"], node_map["fpm"],
        legs_idx, node_map["body"],
    ])
    N("world", children=[pkg_idx])

    b.export(output_path)

    def pt(nodes, idx, indent=0):
        n = nodes[idx]
        print(" " * indent + f"├── {n.name}")
        if n.children:
            for c in n.children:
                pt(nodes, c, indent + 4)
    print("\nHierarchy:")
    pt(b.nodes, 0)
    print(f"\nNodes: {len(b.nodes)}, Meshes: {len(b.mesh_defs)}, Materials: {len(b.materials)}")
    return True


if __name__ == "__main__":
    build_dip8()
