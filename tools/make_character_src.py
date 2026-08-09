"""ONE-TIME extraction: build assets/src/character.blend from the world file.

Produces a standalone character source at real-world scale (1.55 m, feet at
origin, transforms applied) with the staff bone-parented to the right hand and
all animations. After this, character editing happens HERE, and
tools/unicorn_cleanup.py exports it without any transform surgery.
"""
import json
import sys
import traceback

import bpy
from mathutils import Matrix

SRC = "/Users/michellepaulson/gauntlet/assets/src/inferno_world.blend"
DST = "/Users/michellepaulson/gauntlet/assets/src/character.blend"
TARGET_HEIGHT = 1.55


def action_channelbags(a):
    for layer in a.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield bag


def main():
    bpy.ops.wm.open_mainfile(filepath=SRC)
    stats = {}

    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    emp = arm.parent
    descendants = list(arm.children_recursive)
    uni = next(c for c in descendants
               if c.type == "MESH" and any(m.type == "ARMATURE" for m in c.modifiers))
    props = [c for c in descendants if c is not uni]
    keep = {arm, uni} | set(props) | ({emp} if emp else set())
    for ob in list(bpy.data.objects):
        if ob not in keep:
            bpy.data.objects.remove(ob, do_unlink=True)
    for ob in list(bpy.data.objects):
        ob.name = ob.name.removesuffix("-noimp")

    # character actions only
    keep_actions = {"run", "walk", "idle", "light", "attack_1", "attack_2",
                    "react_minor", "react_major", "death", "turn_left", "turn_right"}
    for act in list(bpy.data.actions):
        if act.name not in keep_actions:
            bpy.data.actions.remove(act)

    # rest pose, placement zeroed
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    if emp:
        emp.location = (0.0, 0.0, 0.0)
        emp.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    # record world poses of props (post placement-zero, rest pose)
    prop_world = {ob.name: ob.matrix_world.copy() for ob in props}

    # flatten: bake the import chain into the data, world-preserving
    m_arm = arm.matrix_world.copy()
    m_uni = uni.matrix_world.copy()
    uni.parent = None
    uni.matrix_world = m_uni
    arm.parent = None
    arm.matrix_world = m_arm
    if emp:
        bpy.data.objects.remove(emp, do_unlink=True)
    arm.data.transform(m_arm)
    arm.matrix_world = Matrix.Identity(4)
    uni.data.transform(m_uni)
    uni.matrix_world = Matrix.Identity(4)
    uni.parent = arm

    # rescale pose-location keys into the new rest space
    scale_factor = m_arm.to_scale().x
    for act in bpy.data.actions:
        for bag in action_channelbags(act):
            for fc in list(bag.fcurves):
                if not fc.data_path.startswith("pose.bones"):
                    bag.fcurves.remove(fc)
                elif fc.data_path.endswith(".location"):
                    for kp in fc.keyframe_points:
                        kp.co[1] *= scale_factor
                        kp.handle_left[1] *= scale_factor
                        kp.handle_right[1] *= scale_factor
                    fc.update()
    bpy.context.view_layer.update()

    # normalize height
    ws = [uni.matrix_world @ v.co for i, v in enumerate(uni.data.vertices) if i % 7 == 0]
    height = max(v.z for v in ws) - min(v.z for v in ws)
    f = TARGET_HEIGHT / height
    norm = Matrix.Scale(f, 4)
    arm.data.transform(norm)
    uni.data.transform(norm)
    for act in bpy.data.actions:
        for bag in action_channelbags(act):
            for fc in bag.fcurves:
                if fc.data_path.endswith(".location"):
                    for kp in fc.keyframe_points:
                        kp.co[1] *= f
                        kp.handle_left[1] *= f
                        kp.handle_right[1] *= f
                    fc.update()
    stats["height_factor"] = round(f, 4)
    bpy.context.view_layer.update()

    # place props back: world pose scaled by the same normalization
    for name, w in prop_world.items():
        ob = bpy.data.objects.get(name)
        if ob is not None:
            ob.matrix_world = Matrix.Scale(f, 4) @ w
    bpy.context.view_layer.update()

    # texture diet
    for img in bpy.data.images:
        if img.name in ("Render Result", "Viewer Node"):
            continue
        try:
            if max(img.size) > 512:
                s = 512 / max(img.size)
                img.scale(max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s)))
                img.pack()
        except Exception:
            pass

    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=DST)
    stats["saved"] = DST
    stats["objects"] = sorted(o.name for o in bpy.data.objects)
    stats["actions"] = sorted(a.name for a in bpy.data.actions)
    print("CHARSRC_RESULT " + json.dumps(stats))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
