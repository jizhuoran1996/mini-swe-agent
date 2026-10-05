"""Consumer stage 2: reload the produced blend in a fresh Blender process,
assert persisted scene semantics, and emit a second CPU Cycles frame.
"""
import sys
from pathlib import Path

import bpy


if "--" not in sys.argv:
    raise SystemExit("workdir argument missing")
workdir = Path(sys.argv[sys.argv.index("--") + 1])
blend_path = workdir / "scene.blend"
first_frame = workdir / "frame.png"

if not blend_path.is_file():
    raise SystemExit(f"blend file missing: {blend_path}")
if not first_frame.is_file() or first_frame.stat().st_size == 0:
    raise SystemExit("producer frame missing or empty")

bpy.ops.wm.open_mainfile(filepath=str(blend_path))

obj = bpy.data.objects.get("BevelCube")
assert obj is not None, "BevelCube object missing after reload"
assert obj.type == "MESH", "BevelCube is not a mesh"
assert len(obj.data.vertices) > 8, (
    f"bevel geometry was not persisted ({len(obj.data.vertices)} verts)"
)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.render.resolution_x = 64
scene.render.resolution_y = 64
scene.render.image_settings.file_format = "PNG"
second_frame = workdir / "frame2.png"
scene.render.filepath = str(second_frame)

bpy.ops.render.render(write_still=True)

assert second_frame.is_file() and second_frame.stat().st_size > 0, (
    "reload render frame missing"
)
print("VERIFY_OK", "verts=", len(obj.data.vertices),
      "png_bytes=", second_frame.stat().st_size)
