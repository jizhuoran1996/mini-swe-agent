"""Consumer stage 1: build a fresh scene, save it and CPU-render a frame.
Invoked as::
    blender --background --factory-startup --python scene_produce.py -- <workdir>
"""
import sys
from pathlib import Path

import bmesh
import bpy


if "--" not in sys.argv:
    raise SystemExit("workdir argument missing")
workdir = Path(sys.argv[sys.argv.index("--") + 1])
workdir.mkdir(parents=True, exist_ok=True)
blend_path = workdir / "scene.blend"
frame_path = workdir / "frame.png"

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.mesh.primitive_cube_add(size=2.0)
obj = bpy.context.active_object
obj.name = "BevelCube"
mesh = obj.data

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
