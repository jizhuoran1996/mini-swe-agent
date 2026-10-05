import bpy
import os
import sys

argv = sys.argv
workdir = argv[argv.index("--") + 1] if "--" in argv else os.getcwd()

bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new("core_cube")
obj = bpy.data.objects.new("core_cube", mesh)
bpy.context.scene.collection.objects.link(obj)

mesh.from_pydata(
    [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
     (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)], [],
    [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
     (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
)
mesh.update()

bpy.context.view_layer.objects.active = obj
obj.select_set(True)

bevel = obj.modifiers.new(name="bevel", type="BEVEL")
bevel.width = 0.05
bevel.segments = 2
bpy.context.view_layer.update()

depsgraph = bpy.context.evaluated_depsgraph_get()
evaluated = obj.evaluated_get(depsgraph)
beveled = bpy.data.meshes.new_from_object(evaluated)
beveled.name = "core_cube_beveled"
new_obj = bpy.data.objects.new("core_cube_beveled", beveled)
bpy.context.scene.collection.objects.link(new_obj)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.resolution_x = 64
scene.render.resolution_y = 64
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(workdir, "frame.png")

cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = (3.0, -3.0, 2.5)
cam.rotation_euler = (1.1, 0.0, 0.78)
scene.camera = cam

light_data = bpy.data.lights.new("sun", type="SUN")
light = bpy.data.objects.new("sun", light_data)
bpy.context.scene.collection.objects.link(light)
light.location = (4.0, -4.0, 6.0)

scene.cycles.samples = 8

blend_path = os.path.join(workdir, "scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

bpy.ops.render.render(write_still=True)

print("PRODUCE_OK", len(beveled.vertices), len(beveled.polygons), blend_path)
