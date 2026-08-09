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

SRC_CANDIDATES = [
    "/Users/michellepaulson/gauntlet/assets/src/inferno_world.blend",
    "/Users/michellepaulson/gauntlet/assets/inferno_world.blend",
]
DST_GLB = "/Users/michellepaulson/gauntlet/assets/inferno_baked.glb"
CELL = 48.0

# surfaces the player walks on -> merged with -col (trimesh collision)
WALKABLE_PREFIXES = ("Platform", "Bridge", "Mound", "Stair", "Beam", "Bracing",
                     "Column", "Tower", "Ruin", "Box", "StoneArc")
# dense decor -> decimated harder in the bake
DECIMATE_PREFIXES = ("Grass", "Bush", "Crag", "Rock", "Stone", "GoldPile", "Coal",
                     "Bone", "Spike", "Crystal", "Chain", "Brazier", "Vase",
                     "SilverBar", "Cliff", "Mountain")
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


def main():
    src = next((p for p in SRC_CANDIDATES if os.path.exists(p)), None)
    if src is None:
        raise RuntimeError("no inferno_world.blend found")
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

    # --- classify meshes ---
    lava_planes = []
    groups: dict = {}   # (kind, mat, cx, cy) -> [objects]
    keep_alone = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            keep_alone.append(ob)
            continue
        p = prefix_of(ob.name)
        if p == "Lava" and max(ob.dimensions.x, ob.dimensions.y) > 300:
            lava_planes.append(ob)
            continue
        if p == "Sky":
            keep_alone.append(ob)
            continue
        mat = ob.data.materials[0].name if ob.data.materials and ob.data.materials[0] else "none"
        walk = any(p.startswith(w) for w in WALKABLE_PREFIXES)
        dec = any(p.startswith(d) for d in DECIMATE_PREFIXES)
        loc = ob.matrix_world.translation
        key = ("walk" if walk else ("dec" if dec else "misc"), mat,
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
        if kind == "walk":
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
    RATIOS = {"dec": DECIMATE_RATIO, "misc": 0.5, "walk": 0.6}
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

    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.export_scene.gltf(filepath=DST_GLB, export_format="GLB")
    stats["saved"] = DST_GLB
    print("BAKE_RESULT " + json.dumps(stats))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
