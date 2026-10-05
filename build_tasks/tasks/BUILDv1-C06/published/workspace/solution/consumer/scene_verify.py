import bpy
import os
import sys

argv = sys.argv
workdir = argv[argv.index("--") + 1] if "--" in argv else os.getcwd()

blend_path = os.path.join(workdir, "scene.blend")
bpy.ops.wm.open_mainfile(filepath=blend_path)

obj = bpy.data.objects.get("core_cube_beveled")
assert obj is not None, "reloaded scene is missing the beveled object"
mesh = obj.data
assert mesh is not None, "reloaded object has no mesh"
assert len(mesh.vertices) > 8, f"bevel did not persist: only {len(mesh.vertices)} vertices"
assert len(mesh.polygons) > 6, f"bevel did not persist: only {len(mesh.polygons)} faces"

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.resolution_x = 64
scene.render.resolution_y = 64
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(workdir, "frame2.png")
scene.cycles.samples = 8

if scene.camera is None:
    for candidate in bpy.data.objects:
        if candidate.type == "CAMERA":
            scene.camera = candidate
            break
assert scene.camera is not None, "no camera survived the reload"

bpy.ops.render.render(write_still=True)

print("VERIFY_OK", len(mesh.vertices), len(mesh.polygons))
