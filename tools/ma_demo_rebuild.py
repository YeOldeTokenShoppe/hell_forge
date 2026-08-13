"""Rebuild a Synty Maya-ASCII (.ma) demo scene in Blender.

Synty demo .ma files are placement lists: transform nodes named after the
pack's SM_* FBX pieces, with local TRS in setAttr lines. This parses the
transforms, composes world matrices (Maya Y-up), converts to Blender Z-up,
imports each unique FBX once, and places linked duplicates — an editable,
instanced .blend, no Maya required.

Run (defaults to the Mini Fantasy hex islands demo):
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/ma_demo_rebuild.py -- \
        [path/to/Demo.ma] [path/to/FBX_dir] [path/to/Textures_dir] [out.blend]
"""
import json
import os
import re
import sys
import traceback
from math import radians

import bpy
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PACK = "/Users/michellepaulson/Documents/Synty/mini fantasy"
MA = argv[0] if len(argv) > 0 else os.path.join(
    PACK, "Polygon_Mini_Hex_Islands_Demo.ma")
FBX_DIR = argv[1] if len(argv) > 1 else os.path.join(PACK, "FBX")
TEX_DIR = argv[2] if len(argv) > 2 else os.path.join(PACK, "Textures")
OUT = argv[3] if len(argv) > 3 else (
    "/Users/michellepaulson/gauntlet/assets/src/"
    + os.path.splitext(os.path.basename(MA))[0].lower() + ".blend")

CREATE_RE = re.compile(r'createNode transform -n "([^"]+)"(?: -p "([^"]+)")?')
SETATTR_RE = re.compile(
    r'setAttr "\.([trs])" -type "double3" ([-\d.e]+) ([-\d.e]+) ([-\d.e]+)')
MESH_RE = re.compile(r'createNode mesh -n "[^"]+" -p "([^"]+)"')
FLOAT_RE = re.compile(r"-?\d+\.?\d*(?:e-?\d+)?")


def parse_shape_bboxes(path):
    """Bounding box of each transform's inline mesh, in .ma local space —
    ground truth for how each piece is oriented in the scene file."""
    boxes = {}
    parent = None
    in_vt = False
    lo = hi = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            m = MESH_RE.search(line)
            if m:
                if parent and lo:
                    boxes[parent] = (lo, hi)
                parent = m.group(1)
                lo = hi = None
                in_vt = False
                continue
            if line.startswith("createNode") and "mesh" not in line:
                if parent and lo:
                    boxes[parent] = (lo, hi)
                parent = None
                in_vt = False
                continue
            if parent is None:
                continue
            stripped = line.strip()
            if stripped.startswith('setAttr ".vt['):
                in_vt = True
                stripped = stripped.split('"float3"')[-1]
            elif in_vt and stripped.startswith("setAttr"):
                in_vt = False
            if in_vt:
                nums = [float(x) for x in FLOAT_RE.findall(stripped)]
                for i in range(0, len(nums) - 2, 3):
                    v = nums[i:i + 3]
                    if lo is None:
                        lo = list(v)
                        hi = list(v)
                    else:
                        for a in range(3):
                            lo[a] = min(lo[a], v[a])
                            hi[a] = max(hi[a], v[a])
                if stripped.rstrip().endswith(";"):
                    in_vt = False
    if parent and lo:
        boxes[parent] = (lo, hi)
    return boxes


def orient_fix(mesh, ma_box):
    """Rotate mesh data so its bbox matches the .ma shape's bbox — the OBJ
    exports mix Y-up and Z-up per piece."""
    lo, hi = ma_box
    xs = [v.co for v in mesh.vertices]
    obj_lo = [min(c[i] for c in xs) for i in range(3)]
    obj_hi = [max(c[i] for c in xs) for i in range(3)]
    obj_ext = [obj_hi[i] - obj_lo[i] for i in range(3)]
    ma_ext = [hi[i] - lo[i] for i in range(3)]
    # .ma vertex data is centimeters regardless of declared units —
    # compare shapes scale-free
    s_obj = max(obj_ext) or 1.0
    s_ma = max(ma_ext) or 1.0
    o = [e / s_obj for e in obj_ext]
    m = [e / s_ma for e in ma_ext]

    def close(a, b):
        return abs(a - b) <= 0.08

    if close(o[1], m[1]) and close(o[2], m[2]):
        return  # already matches
    if close(o[1], m[2]) and close(o[2], m[1]):
        # y/z swapped: decide Rx(+90) vs Rx(-90) by bbox center sign
        ma_cy = (lo[1] + hi[1]) / 2 / s_ma
        obj_cz = (obj_lo[2] + obj_hi[2]) / 2 / s_obj
        angle = radians(90) if abs(-obj_cz - ma_cy) <= abs(obj_cz - ma_cy) \
            else radians(-90)
        mesh.transform(Matrix.Rotation(angle, 4, "X"))


def parse_ma(path):
    nodes = {}
    current = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            m = CREATE_RE.search(line)
            if m:
                current = m.group(1)
                nodes[current] = {"parent": m.group(2),
                                  "t": (0, 0, 0), "r": (0, 0, 0),
                                  "s": (1, 1, 1)}
                continue
            if line.startswith("createNode"):
                current = None
                continue
            if current:
                m = SETATTR_RE.search(line)
                if m:
                    nodes[current][m.group(1)] = tuple(
                        float(m.group(i)) for i in (2, 3, 4))
    return nodes


def local_matrix(n):
    t = Matrix.Translation(Vector(n["t"]))
    r = Euler(tuple(radians(a) for a in n["r"]), "XYZ").to_matrix().to_4x4()
    s = Matrix.Diagonal(Vector(n["s"]).to_4d())
    return t @ r @ s


def world_matrix(name, nodes, cache):
    if name in cache:
        return cache[name]
    n = nodes[name]
    m = local_matrix(n)
    if n["parent"] and n["parent"] in nodes:
        m = world_matrix(n["parent"], nodes, cache) @ m
    cache[name] = m
    return m


def fbx_lookup(fbx_dir):
    table = {}
    for f in os.listdir(fbx_dir):
        if f.lower().endswith(".fbx"):
            table[os.path.splitext(f)[0].lower()] = os.path.join(fbx_dir, f)
    return table


def match_fbx(name, table):
    # the .ma scene says "Colunm", the shipped files say "Column" —
    # Synty fixed their typo in only one place
    for fixed in (name, name.replace("Colunm", "Column")):
        parts = fixed.split("_")
        for k in range(len(parts), 1, -1):
            cand = "_".join(parts[:k]).lower()
            if cand in table:
                return table[cand]
            if cand + "_01" in table:
                return table[cand + "_01"]
    return None


def is_binary_fbx(path):
    with open(path, "rb") as f:
        return f.read(18) == b"Kaydara FBX Binary"


def import_piece(path):
    """Returns (mesh, data_is_zup). OBJ twins keep raw Maya Y-up vertex
    data, so their instances skip the model-space half of the conversion."""
    before = set(bpy.data.objects)
    data_is_zup = True
    if path.lower().endswith(".fbx") and not is_binary_fbx(path):
        # ASCII FBX (Mini Fantasy pack): Blender can't read it — use the
        # pack's OBJ twin instead
        obj_path = os.path.join(
            os.path.dirname(os.path.dirname(path)), "OBJ",
            os.path.splitext(os.path.basename(path))[0] + ".obj")
        if not os.path.exists(obj_path):
            return None, True
        bpy.ops.wm.obj_import(filepath=obj_path)
        data_is_zup = False
    else:
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        return None, True
    if len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.join()
    ob = meshes[0]
    # bake the importer's axis/unit conversion straight into the mesh —
    # bpy.ops.object.transform_apply silently no-ops in background mode
    ob.data.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    for o in new:
        if o is not ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    # the OBJ importer's unit handling is inconsistent — a "mini" piece
    # larger than 50 m means centimeter data slipped through; normalize
    if max(ob.dimensions) > 50.0:
        ob.data.transform(Matrix.Scale(0.01, 4))
    mesh = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    return mesh, data_is_zup


def pick_atlas(pngs):
    # prefer the pack's main color atlas over FX/emission variants
    for f in pngs:
        if "Texture_01" in f and not re.search(r"Blue|Green|Purple|Red|Yellow", f):
            return f
    return pngs[0] if pngs else None


def fix_materials():
    wired = 0
    pngs = sorted(f for f in os.listdir(TEX_DIR) if f.lower().endswith(".png"))
    atlas = pick_atlas(pngs)
    fallback = os.path.join(TEX_DIR, atlas) if atlas else None
    if fallback:
        atlas_img = bpy.data.images.load(fallback, check_existing=True)
        # Maya-exported .mtl files carry dead absolute paths: image nodes
        # exist but are 0x0 husks — repoint every broken image at the atlas
        for img in list(bpy.data.images):
            if img is not atlas_img and (img.size[0] == 0 or not img.has_data):
                img.filepath = fallback
                img.reload()
                if img.size[0] == 0:
                    for mat in bpy.data.materials:
                        if not mat.use_nodes:
                            continue
                        for n in mat.node_tree.nodes:
                            if n.type == "TEX_IMAGE" and n.image is img:
                                n.image = atlas_img
                                wired += 1
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = next((n for n in mat.node_tree.nodes
                     if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        if not bsdf.inputs["Metallic"].is_linked:
            bsdf.inputs["Metallic"].default_value = 0.0  # synty chrome bug
        bsdf.inputs["Roughness"].default_value = 0.9
        base = bsdf.inputs["Base Color"]
        has_img = any(n.type == "TEX_IMAGE" and n.image and n.image.size[0] > 0
                      for n in mat.node_tree.nodes)
        if has_img or fallback is None:
            continue
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(fallback, check_existing=True)
        node.location = (-350, 200)
        mat.node_tree.links.new(node.outputs["Color"], base)
        wired += 1
    return wired


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nodes = parse_ma(MA)
    shapes = parse_shape_bboxes(MA)
    table = fbx_lookup(FBX_DIR)
    conv = Matrix.Rotation(radians(90), 4, "X")
    conv_i = conv.inverted()
    cache = {}
    mesh_cache = {}
    placed = 0
    unmatched = {}
    for name in nodes:
        fbx = match_fbx(name, table)
        if fbx is None:
            unmatched[name.rsplit("_", 1)[0]] = \
                unmatched.get(name.rsplit("_", 1)[0], 0) + 1
            continue
        if fbx not in mesh_cache:
            piece_mesh, zup = import_piece(fbx)
            if piece_mesh is not None:
                box = next((shapes[n] for n in nodes
                            if n in shapes and match_fbx(n, table) == fbx),
                           None)
                if box is not None:
                    orient_fix(piece_mesh, box)
            mesh_cache[fbx] = (piece_mesh, zup)
        mesh, data_is_zup = mesh_cache[fbx]
        if mesh is None:
            continue
        ob = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(ob)
        m = conv @ world_matrix(name, nodes, cache)
        ob.matrix_world = m @ conv_i if data_is_zup else m
        placed += 1
    wired = fix_materials()
    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("MA_REBUILD " + json.dumps({
        "ma": os.path.basename(MA), "transforms": len(nodes),
        "placed": placed, "unique_pieces": len(mesh_cache),
        "materials_wired": wired, "unmatched": unmatched, "saved": OUT}))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
