"""Export a Mixamo-friendly FBX of the character from character.blend.

Skin + skeleton only: no staff, no animations, rest pose. The rig keeps its
mixamorig:* names so Mixamo recognizes the skeleton outright.
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/mixamo_export.py
Upload the result at assets/src/unicorn_for_mixamo.fbx to mixamo.com.
"""
import os
import sys
import traceback

import bpy
from mathutils import Matrix

SRC = "/Users/michellepaulson/gauntlet/assets/src/character.blend"
DST = "/Users/michellepaulson/gauntlet/assets/src/unicorn_for_mixamo.fbx"


def main():
    bpy.ops.wm.open_mainfile(filepath=SRC)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    uni = next(c for c in arm.children_recursive
               if c.type == "MESH" and any(m.type == "ARMATURE" for m in c.modifiers))

    # skin + bones only
    for ob in list(bpy.data.objects):
        if ob not in (arm, uni):
            bpy.data.objects.remove(ob, do_unlink=True)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    if arm.animation_data:
        arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)

    for ob in bpy.data.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(
        filepath=DST,
        use_selection=True,
        add_leaf_bones=False,
        bake_anim=False,
        mesh_smooth_type="OFF",
        apply_unit_scale=True,
    )
    print("MIXAMO_EXPORT", DST, os.path.getsize(DST))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
