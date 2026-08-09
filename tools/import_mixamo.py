"""Merge downloaded Mixamo animation FBXs into character.blend.

Workflow:
  1. Upload assets/src/unicorn_for_mixamo.fbx to mixamo.com
  2. Pick an animation, download as FBX (Without Skin is fine)
  3. Drop the file into assets/src/mixamo_inbox/ named as the animation
     should be called in the game (e.g. wave.fbx -> "wave")
  4. Run:  /Applications/Blender.app/Contents/MacOS/Blender --background \
               --python tools/import_mixamo.py
  5. Then the usual: tools/unicorn_cleanup.py + tools/build_web.sh

Handles the scale mismatch between Mixamo's units and the normalized
character rig by rescaling location keys from the skeleton height ratio.
"""
import glob
import json
import os
import sys
import traceback

import bpy

SRC = "/Users/michellepaulson/gauntlet/assets/src/character.blend"
INBOX = "/Users/michellepaulson/gauntlet/assets/src/mixamo_inbox"


def channelbags(a):
    for layer in a.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield bag


def bone_scale_of(arm) -> float:
    b = arm.data.bones.get("mixamorig:Spine")
    return b.length if b else 1.0


def main():
    files = sorted(glob.glob(os.path.join(INBOX, "*.fbx")))
    if not files:
        print("MIXAMO_IMPORT no files in inbox")
        return
    bpy.ops.wm.open_mainfile(filepath=SRC)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    my_scale = bone_scale_of(arm)
    added = []

    for path in files:
        before = set(bpy.data.objects)
        before_actions = set(bpy.data.actions)
        bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True)
        new_objs = [o for o in bpy.data.objects if o not in before]
        new_acts = [a for a in bpy.data.actions if a not in before_actions]
        imported_arm = next((o for o in new_objs if o.type == "ARMATURE"), None)
        if imported_arm is None or not new_acts:
            print(f"SKIP {os.path.basename(path)}: no armature/action found")
            for o in new_objs:
                bpy.data.objects.remove(o, do_unlink=True)
            continue

        factor = my_scale / bone_scale_of(imported_arm)
        act = new_acts[0]
        act.name = os.path.splitext(os.path.basename(path))[0]
        for bag in channelbags(act):
            for fc in list(bag.fcurves):
                if not fc.data_path.startswith("pose.bones"):
                    bag.fcurves.remove(fc)
                elif fc.data_path.endswith(".location"):
                    for kp in fc.keyframe_points:
                        kp.co[1] *= factor
                        kp.handle_left[1] *= factor
                        kp.handle_right[1] *= factor
                    fc.update()
        for a in new_acts[1:]:
            bpy.data.actions.remove(a)
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)

        # bind to the character and stash as an NLA track like the others
        if arm.animation_data is None:
            arm.animation_data_create()
        arm.animation_data.action = act
        if act.slots:
            arm.animation_data.action_slot = act.slots[0]
        track = arm.animation_data.nla_tracks.new()
        track.name = act.name
        track.strips.new(act.name, 1, act)
        arm.animation_data.action = None
        added.append({"anim": act.name, "scale_factor": round(factor, 5)})
        os.rename(path, path + ".imported")

    for _ in range(3):
        bpy.data.orphans_purge(do_recursive=True)
    bpy.ops.wm.save_mainfile()
    print("MIXAMO_IMPORT " + json.dumps(added))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
