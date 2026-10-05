"""Consumer stage 2: reload the produced blend and assert scene semantics.

Runs inside a second independent headless Blender process.
"""
import sys
from pathlib import Path

import bpy


work = Path(sys.argv[sys.argv.index("--") + 1])
blend_path = work / "scene.blend"
frame_path = work / "frame.png"

bpy.ops.wm.open_mainfile(filepath=str(blend_path))

obj = bpy.data.objects.get("BevelCube")
assert obj is not None, "BevelCube object missing after reload"
assert obj.type == "MESH", "BevelCube is not a mesh"
assert len(obj.data.vertices) > 8, "bevel geometry was not persisted"
assert frame_path.is_file() and frame_path.stat().st_size > 0, "render frame missing"

print("VERIFY_OK", "verts=", len(obj.data.vertices), "png_bytes=", frame_path.stat().st_size)
