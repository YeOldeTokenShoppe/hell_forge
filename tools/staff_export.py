"""Export the staff (with Michelle's in-hand placement) as assets/staff.glb.

The staff geometry is baked into the RightHand bone's HEAD frame at final
game scale, so mounting it under a Godot BoneAttachment3D with an identity
transform reproduces the authored grip exactly. Re-run after re-tuning the
staff in Blender:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/staff_export.py
"""
import json
import sys
import traceback

import math

import bpy
from mathutils import Matrix

SRC = "/Users/michellepaulson/gauntlet/assets/src/inferno_world.blend"
DST = "/Users/michellepaulson/gauntlet/assets/staff.glb"
TARGET_HEIGHT = 1.55  # must match unicorn_cleanup.py


def main():
    bpy.ops.wm.open_mainfile(filepath=SRC)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")

    # rest pose, no action — same reference frame the character pipeline uses
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()

    staff = bpy.data.objects["Staff"]
    tip = bpy.data.objects.get("Staff_tip")
    bone_name = staff.parent_bone or "mixamorig:RightHand"
    bone = arm.data.bones[bone_name]
    head = arm.matrix_world @ bone.matrix_local  # glTF joints use the HEAD frame

    # final scale: import chain x height normalization (recomputed from scratch)
    skinned = next(c for c in arm.children_recursive
                   if c.type == "MESH" and any(m.type == "ARMATURE" for m in c.modifiers))
    zs = [(skinned.matrix_world @ v.co).z for i, v in enumerate(skinned.data.vertices) if i % 7 == 0]
    height = max(zs) - min(zs)
    # bone space is in armature-data units; meters = data-units x armature
    # world scale x height normalization
    arm_scale = arm.matrix_world.to_scale().x
    total = arm_scale * (TARGET_HEIGHT / height)

    out = []
    for ob in (staff, tip):
        if ob is None:
            continue
        me = ob.data.copy()
        # change of basis C @ rel @ C^-1 (C = Rx(-90)) maps the Blender
        # bone-relative frame into the glTF/Godot joint frame — verified
        # empirically against the authored grip (candidate fan, 2026-08-08)
        conv = Matrix.Rotation(math.radians(-90.0), 4, "X")
        rel = Matrix.Scale(total, 4) @ head.inverted() @ ob.matrix_world
        me.transform(conv @ rel @ conv.inverted())
        new = bpy.data.objects.new(ob.name, me)
        for mat in ob.data.materials:
            if mat:
                new.data.materials.append(mat)
        bpy.context.scene.collection.objects.link(new)
        out.append(new)

    for ob in list(bpy.data.objects):
        if ob not in out:
            bpy.data.objects.remove(ob, do_unlink=True)
    for ob in out:  # reclaim canonical names now that the originals are gone
        ob.name = ob.name.removesuffix(".001")
        ob.data.name = ob.name
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)

    bpy.ops.export_scene.gltf(filepath=DST, export_format="GLB")
    print("STAFF_RESULT " + json.dumps({
        "bone": bone_name, "total_scale": round(total, 5),
        "objects": [o.name for o in out], "saved": DST,
    }))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
