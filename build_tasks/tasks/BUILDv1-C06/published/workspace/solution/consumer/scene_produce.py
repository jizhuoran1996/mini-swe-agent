"""Consumer stage 1: build a scene from scratch and render one CPU frame.

Runs inside an installed headless Blender:
    blender --background --factory-startup --python scene_produce.py -- <workdir>
"""
import sys
from pathlib import Path

import bmesh
import bpy


work = Path(sys.argv[sys.argv.index("--") + 1])
work.mkdir(parents=True, exist_ok=True)
blend_path = work / "scene.blend"
frame_path = work / "frame.png"

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.mesh.primitive_cube_add(size=2.0)
cube = bpy.context.active_object
cube.name = "BevelCube"
mesh = cube.data

bm = bmesh.new()
bm.from_mesh(mesh)
bmesh.ops.bevel(
    bm,
    geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
    offset=0.15,
    segments=2,
    affect="EDGES",
)
bm.to_mesh(mesh)
bm.free()
mesh.update()

bpy.ops.object.camera_add(location=(5.0, -5.0, 4.0))
camera = bpy.context.active_object
camera.rotation_euler = (1.1, 0.0, 0.785)
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type="SUN", location=(3.0, -3.0, 5.0))

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.render.resolution_x = 64
scene.render.resolution_y = 64
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(frame_path)

bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)

print("PRODUCE_OK", blend_path, frame_path, len(mesh.vertices))
