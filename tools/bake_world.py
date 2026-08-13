"""Bake the editable inferno world into a game-ready level.

Reads assets/src/inferno_world.blend (falls back to assets/inferno_world.blend),
merges scatter by (material x 48m cell), decimates dense decor, drops lights and
helper objects, marks walkable surfaces -col and lava planes as kill zones,
and saves assets/inferno_baked.blend for Godot to import.

Run after ANY world edit:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/bake_world.py
"""
import json
import os
import sys
import traceback

import bpy

# first existing source wins; the destination GLB follows it
SRC_DST = [
    ("/Users/michellepaulson/gauntlet/assets/src/bank_world.blend",
     "/Users/michellepaulson/gauntlet/assets/bank_baked.glb"),
    ("/Users/michellepaulson/gauntlet/assets/src/pirate_realm_island.blend",
     "/Users/michellepaulson/gauntlet/assets/archipelago_baked.glb"),
    ("/Users/michellepaulson/gauntlet/assets/src/pirate_world.blend",
     "/Users/michellepaulson/gauntlet/assets/pirate_baked.glb"),
    ("/Users/michellepaulson/gauntlet/assets/src/inferno_world_v2.blend",
     "/Users/michellepaulson/gauntlet/assets/inferno_baked.glb"),
    ("/Users/michellepaulson/gauntlet/assets/src/inferno_world.blend",
     "/Users/michellepaulson/gauntlet/assets/inferno_baked.glb"),
]
CELL = 48.0

# surfaces the player walks on -> merged with -col (trimesh collision)
WALKABLE_PREFIXES = ("Platform", "Bridge", "Mound", "Stair", "Beam", "Bracing",
                     "Column", "Tower", "Ruin", "Box", "StoneArc")
# dense decor -> decimated harder in the bake
DECIMATE_PREFIXES = ("Grass", "Bush", "Crag", "Rock", "Stone", "GoldPile", "Coal",
                     "Bone", "Spike", "Crystal", "Chain", "Brazier", "Vase",
                     "SilverBar", "Mountain")
# perimeter terrain the player can stand on -> decor decimation but WITH
# collision (-col), so spawning/walking on the map edge doesn't fall through
CLIFF_PREFIXES = ("Cliff",)

# Synty SM_* packs (pirates) bury the meaning mid-name, so these are
# full-name substring rules that extend the prefix lists above
WALKABLE_TOKENS = ("SM_Bld", "_Env_Beach", "_Env_Tile", "_Env_Flat_Sand")
# cutout fabric reads as air but was colliding: keep it decorative
NO_COLLISION_TOKENS = ("Awning", "Netting", "Sail", "Flag", "Rope",
                       "ClothesLine", "StallCover", "Stall_Cloth")
CLIFF_TOKENS = ("_Env_Rock", "_Env_Mangrove_Roots")
DECIMATE_TOKENS = ("_Env_", "_Item_", "_Flag_", "SM_Veh")
KILL_LIQUIDS = ("Lava", "Ocean", "Water")  # all of them consume liquidity
# (kill planes are renamed Lava_XX-col in the bake, so player.gd's
#  existing "Lava" collider check covers every liquid)
DECIMATE_RATIO = 0.35
MAX_TEX = 1024          # color atlases capped at this
MAX_NORMAL_TEX = 256    # normal maps barely read at this art style


def prefix_of(name: str) -> str:
    out = []
    for ch in name:
        if ch in "_. 0123456789":
            break
        out.append(ch)
    return "".join(out)


def patch_stair_cracks():
    """Invisible -colonly quads over holes in big stair walking surfaces.

    The stone-pieced stairs have open seams (widened by non-uniform
    scaling) that a capsule slips through. Rain rays down on a 0.6 m
    grid; any dry cell with wet neighbors gets a collision patch at the
    neighbors' height. Runs per bake, so rescaled stairs self-heal."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import bmesh

    dg = bpy.context.evaluated_depsgraph_get()
    cell = 0.6
    bm = bmesh.new()
    patched = 0
    for ob in list(bpy.data.objects):
        if ob.type != "MESH" or not prefix_of(ob.name).startswith("Stair"):
            continue
        if ob.dimensions.z < 5:
            continue
        bvh = BVHTree.FromObject(ob, dg)
        mw = ob.matrix_world
        mi = mw.inverted()
        corners = [mw @ Vector(c) for c in ob.bound_box]
        x0 = min(c.x for c in corners)
        x1 = max(c.x for c in corners)
        y0 = min(c.y for c in corners)
        y1 = max(c.y for c in corners)
        z_top = max(c.z for c in corners) + 2.0
        nx = int((x1 - x0) / cell) + 1
        ny = int((y1 - y0) / cell) + 1
        if nx * ny > 200000:
            continue
        d_local = (mi.to_3x3() @ Vector((0, 0, -1))).normalized()
        heights = {}
        for ix in range(nx):
            for iy in range(ny):
                origin = mi @ Vector((x0 + (ix + 0.5) * cell,
                                      y0 + (iy + 0.5) * cell, z_top))
                hit = bvh.ray_cast(origin, d_local)
                if hit[0] is not None:
                    heights[(ix, iy)] = (mw @ hit[0]).z
        for ix in range(nx):
            for iy in range(ny):
                if (ix, iy) in heights:
                    continue
                nb = [heights[k] for k in
                      ((ix - 1, iy), (ix + 1, iy), (ix, iy - 1), (ix, iy + 1))
                      if k in heights]
                if len(nb) < 2:
                    continue
                z = max(nb) + 0.02
                cx = x0 + (ix + 0.5) * cell
                cy = y0 + (iy + 0.5) * cell
                h = cell * 0.62  # overlap into neighbors so seams seal
                vs = [bm.verts.new((cx - h, cy - h, z)),
                      bm.verts.new((cx + h, cy - h, z)),
                      bm.verts.new((cx + h, cy + h, z)),
                      bm.verts.new((cx - h, cy + h, z))]
                bm.faces.new(vs)
                patched += 1
    if patched:
        patch_me = bpy.data.meshes.new("bk_crackpatch")
        bm.to_mesh(patch_me)
        patch_ob = bpy.data.objects.new("bk_crackpatch-colonly", patch_me)
        bpy.context.scene.collection.objects.link(patch_ob)
    bm.free()
    return patched


def main():
    src, dst_glb = next(((s, d) for s, d in SRC_DST if os.path.exists(s)),
                        (None, None))
    if src is None:
        raise RuntimeError("no world blend found")
    bpy.ops.wm.open_mainfile(filepath=src)
    stats = {"src": src}
    stats["objects_before"] = len(bpy.data.objects)

    # workaround for a Blender 5.1 join crash (int32 overflow in custom-normal
    # attribute handling on large merges): strip stored custom normals; the
    # pack's Auto Smooth modifiers recompute shading at export time anyway
    stripped = 0
    for me in bpy.data.meshes:
        attr = me.attributes.get("custom_normal")
        if attr is not None:
            me.attributes.remove(attr)
            stripped += 1
    stats["custom_normals_stripped"] = stripped

    # the glTF exporter can't trace math-gated alpha chains (viewport-only
    # clip trick): rewire tex.Alpha directly to BSDF.Alpha and declare
    # CLIP so foliage/fabric export as alphaMode=MASK instead of opaque
    alpha_fixed = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = next((n for n in mat.node_tree.nodes
                     if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None or not bsdf.inputs["Alpha"].is_linked:
            continue
        link = bsdf.inputs["Alpha"].links[0]
        if link.from_node.type == "MATH":
            gate = link.from_node
            src = (gate.inputs[0].links[0].from_socket
                   if gate.inputs[0].is_linked else None)
            mat.node_tree.links.remove(link)
            if src is not None:
                mat.node_tree.links.new(src, bsdf.inputs["Alpha"])
        for attr, val in (("blend_method", "CLIP"),
                          ("alpha_threshold", 0.5),
                          ("surface_render_method", "DITHERED")):
            try:
                setattr(mat, attr, val)
            except (AttributeError, TypeError):
                pass
        alpha_fixed += 1
    stats["alpha_clip_materials"] = alpha_fixed

    # flat-color atlas needs neither vertex colors nor extra UV sets —
    # the pirates meshes carry both, nearly doubling per-vertex cost
    colors_stripped = 0
    for me in bpy.data.meshes:
        for attr in list(me.color_attributes):
            me.color_attributes.remove(attr)
            colors_stripped += 1
        if len(me.uv_layers) > 1:
            # keep the layer Blender actually RENDERS with — index 0 can
            # be a lightmap set (full-atlas smear in game if exported)
            keep = next((l.name for l in me.uv_layers if l.active_render),
                        me.uv_layers[0].name)
            for l in [l for l in me.uv_layers if l.name != keep]:
                me.uv_layers.remove(l)
        if me.uv_layers:
            # one shared name: bmesh merges match UV layers BY NAME, and
            # mixed names silently drop coordinates for half the faces
            me.uv_layers[0].name = "UVMap"
    stats["color_attrs_stripped"] = colors_stripped

    # --- texture diet: the web build ships these ---
    tex_changed = 0
    for img in list(bpy.data.images):
        if img.name in ("Render Result", "Viewer Node"):
            continue
        if img.name.lower().startswith("leadenhall"):
            bpy.data.images.remove(img)
            continue
        limit = MAX_NORMAL_TEX if "normal" in img.name.lower() else MAX_TEX
        if max(img.size) > limit and img.has_data:
            factor = limit / max(img.size)
            img.scale(max(1, int(img.size[0] * factor)), max(1, int(img.size[1] * factor)))
            img.pack()
            tex_changed += 1
    stats["textures_shrunk"] = tex_changed

    # --- drop what the game never needs ---
    removed = 0
    for ob in list(bpy.data.objects):
        kill = (
            ob.type in ("LIGHT", "CAMERA")
            or ob.name.endswith("-noimp")          # character reference lives elsewhere
            or ob.name.lower().startswith("fog")
        )
        if kill:
            bpy.data.objects.remove(ob, do_unlink=True)
            removed += 1
    stats["helpers_removed"] = removed

    # Unity LOD chains: we have no LOD switching, so every level renders
    # at once — keep LOD0, drop the rest
    import re as _re
    lod_removed = 0
    for ob in list(bpy.data.objects):
        if ob.type != "MESH" or not _re.search(r"_LOD[1-9]", ob.name):
            continue
        # only drop an LOD1+ object when its LOD0 twin exists under the
        # SAME parent — hand-placed standalone LOD copies are real content
        parent = ob.parent
        has_lod0_twin = parent is not None and any(
            c is not ob and c.type == "MESH" and "_LOD0" in c.name
            for c in parent.children)
        if has_lod0_twin:
            bpy.data.objects.remove(ob, do_unlink=True)
            lod_removed += 1
    stats["lod_meshes_removed"] = lod_removed
    if bpy.context.scene.world:
        bpy.context.scene.world = None
    print("PHASE helpers_done", flush=True)
    stats["crack_patches"] = patch_stair_cracks()
    print("PHASE crackpatch_done", flush=True)

    # --- classify meshes ---
    lava_planes = []
    groups: dict = {}   # (kind, mat, cx, cy) -> [objects]
    keep_alone = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            keep_alone.append(ob)
            continue
        if ob.name.endswith("-colonly"):
            # invisible collision helpers (generated crack patches, hand-
            # placed ramps) pass through untouched
            keep_alone.append(ob)
            continue
        p = prefix_of(ob.name)
        if (any(k in ob.name for k in KILL_LIQUIDS)
                and max(ob.dimensions.x, ob.dimensions.y) > 80):
            lava_planes.append(ob)
            continue
        if p == "Sky" or "SkyDome" in ob.name:
            keep_alone.append(ob)
            continue
        # candle stations (and ALL their sub-parts, whatever they're named)
        # stay individual objects so the game can wire an interaction to
        # each; roots get trimesh collision (Godot strips the -col suffix
        # on import, name stays Candle_*)
        anc = ob
        is_candle = False
        while anc is not None:
            if prefix_of(anc.name).lower().startswith("candle"):
                is_candle = True
                break
            anc = anc.parent
        if is_candle:
            # collision rides on whatever holds the geometry: a mesh root
            # (old style) or the wax body (chart style, empty root)
            if ((ob.parent is None or "wax" in ob.name.lower())
                    and not ob.name.endswith("-col")):
                ob.name += "-col"
            keep_alone.append(ob)
            continue
        if any(t in ob.name for t in NO_COLLISION_TOKENS):
            kind = "dec"
        elif (any(p.startswith(c) for c in CLIFF_PREFIXES)
                or any(t in ob.name for t in CLIFF_TOKENS)):
            kind = "cliff"
        elif (any(p.startswith(w) for w in WALKABLE_PREFIXES)
                or any(t in ob.name for t in WALKABLE_TOKENS)):
            kind = "walk"
        elif (any(p.startswith(d) for d in DECIMATE_PREFIXES)
                or any(t in ob.name for t in DECIMATE_TOKENS)):
            kind = "dec"
        else:
            kind = "misc"
        loc = ob.matrix_world.translation
        cx = int((loc.x + 2000) // CELL)
        cy = int((loc.y + 2000) // CELL)
        # one group entry PER MATERIAL SLOT: merging whole multi-material
        # objects under their first slot repaints slot-2+ faces with the
        # wrong texture (and turns walls glass when slot 1 is glass)
        n_slots = max(1, len(ob.data.materials))
        for slot in range(n_slots):
            mat_block = (ob.data.materials[slot]
                         if slot < len(ob.data.materials) else None)
            mat = mat_block.name if mat_block else "none"
            groups.setdefault((kind, mat, cx, cy), []).append((ob, slot))

    # --- merge each group into one object (raw bmesh; bpy.ops.object.join
    # hits an int32-overflow crash in Blender 5.1 on this scene) ---
    print(f"PHASE classify_done groups={len(groups)}", flush=True)
    import bmesh
    merged = []
    consumed = set()
    scene_coll = bpy.context.scene.collection
    for (kind, mat, cx, cy), items in groups.items():
        name = f"bk_{kind}_{mat[:12]}_{cx}_{cy}"
        if kind in ("walk", "cliff"):
            name += "-col"
        bm = bmesh.new()
        for ob, slot in items:
            tmp = ob.data.copy()
            tmp.transform(ob.matrix_world)
            if ob.matrix_world.determinant() < 0:
                # mirrored placement: baking the transform flips winding,
                # and Godot backface-culls the whole piece invisible
                tmp.flip_normals()
            if len(ob.data.materials) > 1:
                bmt = bmesh.new()
                bmt.from_mesh(tmp)
                doomed = [f for f in bmt.faces if f.material_index != slot]
                bmesh.ops.delete(bmt, geom=doomed, context="FACES")
                bmt.to_mesh(tmp)
                bmt.free()
            bm.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
            consumed.add(ob.name)
        if len(bm.faces) == 0:
            bm.free()
            continue
        new_me = bpy.data.meshes.new(name)
        bm.to_mesh(new_me)
        bm.free()
        mat_block = bpy.data.materials.get(mat)
        if mat_block:
            new_me.materials.append(mat_block)
        new_ob = bpy.data.objects.new(name, new_me)
        scene_coll.objects.link(new_ob)
        merged.append((kind, new_ob))
    for ob_name in consumed:
        ob = bpy.data.objects.get(ob_name)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)

    # --- decimate merged cells (per-category ratios) ---
    print("PHASE joins_done", flush=True)
    # walk = architecture the player studies up close: decimation tears
    # slivers along curved trim (bitten arches). Skip it — the bank-scale
    # world has tri budget to spare. Decor/misc keep gentle reduction.
    RATIOS = {"dec": 0.5, "misc": 0.6, "walk": None,
              "cliff": DECIMATE_RATIO}
    for kind, ob in merged:
        ratio = RATIOS.get(kind)
        if ratio is None or ratio >= 1.0:
            continue
        for o in bpy.data.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        mod = ob.modifiers.new("BakeDecimate", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="BakeDecimate")

    # normal maps are invisible at this art style; removing them also lets the
    # importer skip tangent generation (~25% of every vertex)
    unlinked = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        tree = mat.node_tree
        for link in list(tree.links):
            if link.to_socket.name == "Normal":
                tree.links.remove(link)
                unlinked += 1
    for img in list(bpy.data.images):
        if "normal" in img.name.lower():
            bpy.data.images.remove(img)
    stats["normal_links_removed"] = unlinked

    print("PHASE decimates_done", flush=True)
    # --- lava planes: hard decimate + kill-zone collision name ---
    for i, ob in enumerate(lava_planes):
        if ob.data.users > 1:
            ob.data = ob.data.copy()  # instanced meshes can't take modifiers
        for o in bpy.data.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        mod = ob.modifiers.new("BakeDecimate", "DECIMATE")
        # kill planes are flat color + collision; the pirates sea is a
        # 1M-tri wave grid that flattens to almost nothing
        mod.ratio = 0.03
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="BakeDecimate")
        if not ob.name.endswith("-col"):
            ob.name = f"Lava_{i + 1:02d}-col"

    # --- ground height at the pentagram plaza (spawn reference) ---
    plaza_z = None
    for kind, ob in merged:
        if kind != "walk":
            continue
        for v in ob.data.vertices:
            w = ob.matrix_world @ v.co
            if abs(w.x) < 6 and abs(w.y) < 6:
                plaza_z = max(plaza_z, w.z) if plaza_z is not None else w.z
    stats["plaza_top_z"] = round(plaza_z, 2) if plaza_z is not None else None

    total = 0
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            total += sum(len(p.vertices) - 2 for p in ob.data.polygons)
    stats["objects_after"] = len(bpy.data.objects)
    stats["tris_after"] = total
    stats["walk_cells"] = sum(1 for k, _ in merged if k == "walk")
    stats["cliff_cells"] = sum(1 for k, _ in merged if k == "cliff")
    stats["cliff_tris"] = sum(
        sum(len(p.vertices) - 2 for p in ob.data.polygons)
        for k, ob in merged if k == "cliff")

    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.export_scene.gltf(filepath=dst_glb, export_format="GLB")

    # the exporter writes textured cutout materials as BLEND (sorted,
    # flickery, slow) — patch them to MASK in the GLB json; untextured
    # translucents (glass) keep BLEND
    import struct
    with open(dst_glb, "rb") as f:
        magic, version, _total = struct.unpack("<4sII", f.read(12))
        jlen, jtype = struct.unpack("<I4s", f.read(8))
        gltf_json = json.loads(f.read(jlen))
        rest = f.read()
    masked = 0
    for m in gltf_json.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        if m.get("alphaMode") == "BLEND" and "baseColorTexture" in pbr:
            m["alphaMode"] = "MASK"
            m["alphaCutoff"] = 0.5
            masked += 1
        # Synty models plenty of single-sided geometry that its Unity
        # shaders render two-sided; Godot culls it into holes. Cheap at
        # this triangle budget to just disable culling everywhere.
        m["doubleSided"] = True
    payload = json.dumps(gltf_json, separators=(",", ":")).encode()
    payload += b" " * ((4 - len(payload) % 4) % 4)
    with open(dst_glb, "wb") as f:
        f.write(struct.pack("<4sII", magic, version,
                            12 + 8 + len(payload) + len(rest)))
        f.write(struct.pack("<I4s", len(payload), jtype))
        f.write(payload)
        f.write(rest)
    stats["alpha_masked_in_glb"] = masked
    stats["saved"] = dst_glb
    print("BAKE_RESULT " + json.dumps(stats))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
