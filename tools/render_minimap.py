"""Re-render the minimap image from the world source.

Run after world edits change the landscape (new districts, candles, etc.):
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python tools/render_minimap.py
Writes assets/ui/minimap.png. ORTHO must match Balance.MINIMAP_WORLD_SIZE.
"""
import os

import bpy
from mathutils import Vector

ORTHO = 1700.0  # world meters covered; keep in sync with Balance.MINIMAP_WORLD_SIZE

SRC_CANDIDATES = [
    "/Users/michellepaulson/gauntlet/assets/src/pirate_realm_island.blend",
    "/Users/michellepaulson/gauntlet/assets/src/pirate_world.blend",
    "/Users/michellepaulson/gauntlet/assets/src/inferno_world_v2.blend",
]
bpy.ops.wm.open_mainfile(filepath=next(
        p for p in SRC_CANDIDATES if os.path.exists(p)))
scene = bpy.context.scene
cam = bpy.data.objects.new("MapCam", bpy.data.cameras.new("MapCam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = ORTHO
cam.location = Vector((0, 0, 500))
cam.rotation_euler = (0, 0, 0)
cam.data.clip_end = 2000.0
scene.collection.objects.link(cam)
scene.camera = cam
sun = bpy.data.objects.new("MapSun", bpy.data.lights.new("MapSun", "SUN"))
sun.rotation_euler = (0.35, 0.2, 0.4)
sun.data.energy = 3.5
scene.collection.objects.link(sun)
scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.engine = "CYCLES"
scene.cycles.samples = 24
scene.cycles.device = "CPU"
scene.render.image_settings.media_type = "IMAGE"
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = "/Users/michellepaulson/gauntlet/assets/ui/minimap.png"
bpy.ops.render.render(write_still=True)
print("MINIMAP_DONE")
