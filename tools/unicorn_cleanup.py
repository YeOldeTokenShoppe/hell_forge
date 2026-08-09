"""Export the character from assets/src/character.blend to assets/unicorn.glb.

The source file is already clean (real-world scale, transforms applied, staff
bone-parented in Blender) — this script only prunes zero-weight leaf bones,
decimates toward the tri budget, and exports. Bone-parented props (Staff,
Staff_tip) ride through the glTF exporter natively.

Run after ANY character change:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/unicorn_cleanup.py
"""
import json
import sys
import traceback

import bpy

SRC = "/Users/michellepaulson/gauntlet/assets/src/character.blend"
DST = "/Users/michellepaulson/gauntlet/assets/unicorn.glb"
TARGET_TRIS = 2900


def action_channelbags(a):
    for layer in a.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield bag


def tri_count(obj) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def main():
    bpy.ops.wm.open_mainfile(filepath=SRC)
    stats = {}

    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    uni = next(c for c in arm.children_recursive
               if c.type == "MESH" and any(m.type == "ARMATURE" for m in c.modifiers))
    stats["objects"] = sorted(o.name for o in bpy.data.objects)
    stats["actions"] = sorted(a.name for a in bpy.data.actions)

    # --- prune zero-weight leaf bone chains ---
    stats["bones_before"] = len(arm.data.bones)
    idx_to_name = {vg.index: vg.name for vg in uni.vertex_groups}
    wsum: dict = {}
    for v in uni.data.vertices:
        for g in v.groups:
            name = idx_to_name.get(g.group)
            if name:
                wsum[name] = wsum.get(name, 0.0) + g.weight

    def subtree_weight(bone) -> float:
        total: float = wsum.get(bone.name, 0.0)
        for child in bone.children:
            total += subtree_weight(child)
        return total

    # bones that anchor props must survive even if weightless
    prop_bones = {ob.parent_bone for ob in arm.children_recursive
                  if ob.parent_type == "BONE" and ob.parent_bone}

    doomed = {b.name for b in arm.data.bones
              if b.parent is not None and subtree_weight(b) < 0.001
              and b.name not in prop_bones}
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name in doomed:
        eb = arm.data.edit_bones.get(name)
        if eb is not None:
            arm.data.edit_bones.remove(eb)
    bpy.ops.object.mode_set(mode="OBJECT")
    stats["bones_after"] = len(arm.data.bones)

    removed_fc = 0
    for act in bpy.data.actions:
        for bag in action_channelbags(act):
            for fc in list(bag.fcurves):
                if fc.data_path.startswith('pose.bones["'):
                    if fc.data_path.split('"')[1] in doomed:
                        bag.fcurves.remove(fc)
                        removed_fc += 1
    stats["bone_fcurves_removed"] = removed_fc

    # --- decimate (hands shielded) ---
    stats["tris_before"] = tri_count(uni)
    if stats["tris_before"] > TARGET_TRIS:
        protect = uni.vertex_groups.new(name="DecimateProtect")
        hand_idx = {vg.index for vg in uni.vertex_groups if "Hand" in vg.name}
        for v in uni.data.vertices:
            if any(g.group in hand_idx and g.weight > 0.05 for g in v.groups):
                protect.add([v.index], 1.0, "REPLACE")
        mod = uni.modifiers.new("RigDecimate", "DECIMATE")
        mod.ratio = TARGET_TRIS / stats["tris_before"]
        mod.use_collapse_triangulate = True
        mod.vertex_group = "DecimateProtect"
        mod.invert_vertex_group = True
        mod.vertex_group_factor = 10.0
        bpy.context.view_layer.objects.active = uni
        uni.select_set(True)
        bpy.ops.object.modifier_move_to_index(modifier="RigDecimate", index=0)
        bpy.ops.object.modifier_apply(modifier="RigDecimate")
        uni.vertex_groups.remove(uni.vertex_groups["DecimateProtect"])
    stats["tris_after"] = tri_count(uni)

    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.export_scene.gltf(filepath=DST, export_format="GLB")
    stats["saved"] = DST
    print("CLEANUP_RESULT " + json.dumps(stats))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
