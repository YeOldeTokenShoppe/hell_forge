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
CLIFF_TOKENS = ("_Env_Rock", "_Env_Mangrove_Roots")
DECIMATE_TOKENS = ("_Env_", "_Item_", "_Flag_")
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
        mat = ob.data.materials[0].name if ob.data.materials and ob.data.materials[0] else "none"
        if (any(p.startswith(c) for c in CLIFF_PREFIXES)
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
        key = (kind, mat,
               int((loc.x + 2000) // CELL), int((loc.y + 2000) // CELL))
        groups.setdefault(key, []).append(ob)

    # --- merge each group into one object (raw bmesh; bpy.ops.object.join
    # hits an int32-overflow crash in Blender 5.1 on this scene) ---
    print(f"PHASE classify_done groups={len(groups)}", flush=True)
    import bmesh
    merged = []
    scene_coll = bpy.context.scene.collection
    for (kind, mat, cx, cy), objs in groups.items():
        name = f"bk_{kind}_{mat[:12]}_{cx}_{cy}"
        if kind in ("walk", "cliff"):
            name += "-col"
        bm = bmesh.new()
        for ob in objs:
            tmp = ob.data.copy()
            tmp.transform(ob.matrix_world)
            bm.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
        new_me = bpy.data.meshes.new(name)
        bm.to_mesh(new_me)
        bm.free()
        mat_block = bpy.data.materials.get(mat)
        if mat_block:
            new_me.materials.append(mat_block)
        new_ob = bpy.data.objects.new(name, new_me)
        scene_coll.objects.link(new_ob)
        for ob in objs:
            bpy.data.objects.remove(ob, do_unlink=True)
        merged.append((kind, new_ob))

    # --- decimate merged cells (per-category ratios) ---
    print("PHASE joins_done", flush=True)
    RATIOS = {"dec": DECIMATE_RATIO, "misc": 0.5, "walk": 0.6,
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
        for o in bpy.data.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        mod = ob.modifiers.new("BakeDecimate", "DECIMATE")
        mod.ratio = 0.15
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
    stats["saved"] = dst_glb
    print("BAKE_RESULT " + json.dumps(stats))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
