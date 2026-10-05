"""Independent media, geometry and SDK consumers."""
import json
import os
from pathlib import Path
import re
from grader_inside import INSTALL,WORK,execute,find_library


def binary(name):
    p=INSTALL/'bin'/name
    assert p.is_file(),str(p)
    return p


def env():
    return {'PATH':str(INSTALL/'bin')+':'+os.environ['PATH'],
            'LD_LIBRARY_PATH':':'.join(str(p) for p in [INSTALL/'lib',INSTALL/'lib64']),
            'PKG_CONFIG_PATH':':'.join(str(p) for p in [INSTALL/'lib/pkgconfig',INSTALL/'lib64/pkgconfig']),
            'MAGICK_CONFIGURE_PATH':str(INSTALL/'etc/ImageMagick-7')}


def pkg_consumer(name,source,modules,cpp=False,extra_env=None):
    e={**env(),**(extra_env or {})};flags=execute(['pkg-config','--cflags','--libs',*modules],env=e).stdout.decode().split()
    assert any(str(INSTALL) in f for f in flags), 'SDK flags must reference the delivered prefix'
    src=WORK/(name+('.cpp' if cpp else '.c'));src.write_text(source);app=WORK/name
    execute(['g++' if cpp else 'gcc','-O2',src,*flags,'-Wl,-rpath,'+str(INSTALL/'lib'),'-o',app],env=e)
    linkage=execute(['ldd',app],env=e).stdout.decode();assert str(INSTALL) in linkage
    return execute([app],env=e).stdout.decode()


def ffmpeg():
    e=env();ff=binary('ffmpeg');fp=binary('ffprobe')
    execute([ff,'-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=6','-t','1','-c:v','ffv1','new.mkv'],env=e)
    data=json.loads(execute([fp,'-v','error','-show_streams','-of','json','new.mkv'],env=e).stdout)
    s=data['streams'][0];assert s['width']==96 and s['height']==64 and s['codec_name']=='ffv1'
    execute([ff,'-v','error','-i','new.mkv','-vf','scale=48:32','-pix_fmt','rgb24','-f','rawvideo','new.rgb'],env=e)
    raw=(WORK/'new.rgb').read_bytes();assert len(raw)==48*32*3*6 and len(set(raw))>100
    return pkg_consumer('avsdk','#include <libavutil/md5.h>\n#include <string.h>\n#include <stdio.h>\nint main(){unsigned char d[16];av_md5_sum(d,(const unsigned char*)"abc",3);unsigned char e[]={0x90,0x01,0x50,0x98,0x3c,0xd2,0x4f,0xb0,0xd6,0x96,0x3f,0x7d,0x28,0xe1,0x7f,0x72};if(memcmp(d,e,16))return 1;puts("new FFmpeg SDK MD5 passed");return 0;}',['libavutil'])


def gstreamer():
    e=env();e.update(GST_PLUGIN_PATH=str(INSTALL/'lib/gstreamer-1.0'),GST_PLUGIN_SYSTEM_PATH='',GST_REGISTRY=str(WORK/'new-registry.bin'),GST_PLUGIN_SCANNER=str(INSTALL/'libexec/gstreamer-1.0/gst-plugin-scanner'))
    execute([binary('gst-launch-1.0'),'-q','audiotestsrc','num-buffers=10','samplesperbuffer=128','!','audioconvert','!','audio/x-raw,format=S16LE,channels=1,rate=8000','!','wavenc','!','filesink','location=new.wav'],env=e)
    import wave
    with wave.open(str(WORK/'new.wav')) as f:assert f.getnframes()==1280 and f.getframerate()==8000 and f.getnchannels()==1
    return pkg_consumer('gstsdk',r'''
#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <stdio.h>
int main(){gst_init(0,0);GError*err=0;GstElement*p=gst_parse_launch("videotestsrc num-buffers=3 ! video/x-raw,format=RGB,width=24,height=16 ! appsink name=sink",&err);if(!p||err)return 1;
GstElement*s=gst_bin_get_by_name(GST_BIN(p),"sink");gst_element_set_state(p,GST_STATE_PLAYING);int n=0;while(1){GstSample*a=gst_app_sink_pull_sample(GST_APP_SINK(s));if(!a)break;GstBuffer*b=gst_sample_get_buffer(a);if(gst_buffer_get_size(b)!=24*16*3)return 2;n++;gst_sample_unref(a);}gst_element_set_state(p,GST_STATE_NULL);gst_object_unref(s);gst_object_unref(p);if(n!=3)return 3;puts("new GStreamer SDK frame consumer passed");return 0;}
''',['gstreamer-1.0','gstreamer-app-1.0'],extra_env=e)


def imagemagick():
    p=WORK/'new.ppm';p.write_bytes(b'P6\n16 12\n255\n'+bytes([c for y in range(12) for x in range(16) for c in (x*15,y*20,100)]))
    execute([binary('magick'),p,'-resize','8x6!','new.png'],env=env())
    from PIL import Image
    with Image.open(WORK/'new.png') as im:assert im.size==(8,6) and im.getpixel((7,5))[0]>180
    return pkg_consumer('magick_sdk',r'''
#include <MagickWand/MagickWand.h>
#include <stdio.h>
int main(){MagickWandGenesis();MagickWand*w=NewMagickWand();PixelWand*p=NewPixelWand();PixelSetColor(p,"#123456");if(!MagickNewImage(w,13,7,p)||!MagickWriteImage(w,"new_sdk.png"))return 1;if(MagickGetImageWidth(w)!=13||MagickGetImageHeight(w)!=7)return 2;DestroyPixelWand(p);DestroyMagickWand(w);MagickWandTerminus();puts("new MagickWand consumer passed");return 0;}
''',['MagickWand'])


def vips():
    return pkg_consumer('vips_sdk',r'''
#include <vips/vips8>
#include <iostream>
int main(int argc,char**argv){if(VIPS_INIT(argv[0]))return 1;{auto a=vips::VImage::black(18,10)+37;auto b=a.resize(0.5);b.write_to_file("new-vips.png");auto c=vips::VImage::new_from_file("new-vips.png");if(c.width()!=9||c.height()!=5||c.avg()!=37)return 2;}vips_shutdown();std::cout<<"new vips C++ file/resize consumer passed\n";}
''',['vips-cpp'],cpp=True)


def opencv():
    src=WORK/'new_cv.cpp';src.write_text(r'''
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <iostream>
int main(){cv::Mat a(20,30,CV_8UC3,cv::Scalar(10,20,30));cv::rectangle(a,cv::Rect(0,0,10,10),cv::Scalar(200,100,50),-1);if(!cv::imwrite("new_cv.png",a))return 1;auto b=cv::imread("new_cv.png");if(cv::norm(a,b,cv::NORM_INF)!=0)return 2;cv::Mat g;cv::cvtColor(b,g,cv::COLOR_BGR2GRAY);if(g.rows!=20||g.cols!=30)return 3;std::cout<<"new OpenCV codecs/imgproc consumer passed\n";}
''')
    libs=[find_library('opencv_'+n) for n in ['imgcodecs','imgproc','core']]
    app=WORK/'new_cv';execute(['g++','-std=c++17',src,'-I',INSTALL/'include/opencv4',*libs,'-Wl,-rpath,'+str(libs[0].parent),'-o',app]);assert str(INSTALL) in execute(['ldd',app]).stdout.decode();return execute([app]).stdout.decode()


def blender():
    candidates=[p for p in INSTALL.rglob('blender') if p.is_file() and os.access(p,os.X_OK)]
    assert len(candidates)==1;script=WORK/'new_blender.py';script.write_text(r'''
import bpy,json
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=2,location=(1,2,3));o=bpy.context.object;o.name='IndependentCube'
assert len(o.data.vertices)==8 and len(o.data.polygons)==6
bpy.ops.wm.save_as_mainfile(filepath='/workspace/consumer/new.blend')
bpy.ops.wm.open_mainfile(filepath='/workspace/consumer/new.blend')
o=bpy.data.objects['IndependentCube'];assert tuple(o.location)==(1,2,3)
open('/workspace/consumer/blender-result.json','w').write(json.dumps({'vertices':len(o.data.vertices),'location':list(o.location)}))
''');execute([candidates[0],'-b','--factory-startup','--python',script],timeout=300)
    assert json.loads((WORK/'blender-result.json').read_text())=={'vertices':8,'location':[1.,2.,3.]};return 'new headless Blender geometry/save/reload passed'


def godot():
    candidates=[p for p in INSTALL.rglob('*') if p.is_file() and os.access(p,os.X_OK) and p.name.startswith('godot')];assert candidates
    (WORK/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Independent"\n')
    (WORK/'new.gd').write_text('extends SceneTree\nfunc _initialize():\n var a = PackedInt32Array([7, 2, 9, 1])\n a.sort()\n assert(a[0] == 1 and a[3] == 9)\n var f = FileAccess.open("user://independent.json", FileAccess.WRITE)\n f.store_string(JSON.stringify({"sum":19,"values":Array(a)}))\n f.close()\n print("INDEPENDENT_GODOT_OK 19")\n quit()\n')
    result=execute([candidates[0],'--headless','--path',WORK,'--script','new.gd'],timeout=60);assert b'INDEPENDENT_GODOT_OK 19' in result.stdout;return 'new Godot GDScript/container file consumer passed'


def mesa():
    e=env();e.update(LIBGL_ALWAYS_SOFTWARE='1',EGL_PLATFORM='surfaceless',GALLIUM_DRIVER='llvmpipe')
    source=WORK/'new_egl.c';source.write_text(r'''
#include <EGL/egl.h>
#include <GL/gl.h>
#include <string.h>
#include <stdio.h>
int main(){EGLDisplay d=eglGetDisplay(EGL_DEFAULT_DISPLAY);EGLint a,b;if(!eglInitialize(d,&a,&b)||!eglBindAPI(EGL_OPENGL_API))return 1;EGLint attr[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};EGLConfig cfg;EGLint n;if(!eglChooseConfig(d,attr,&cfg,1,&n)||n!=1)return 2;EGLint p[]={EGL_WIDTH,8,EGL_HEIGHT,8,EGL_NONE};EGLSurface s=eglCreatePbufferSurface(d,cfg,p);EGLContext c=eglCreateContext(d,cfg,EGL_NO_CONTEXT,0);if(!eglMakeCurrent(d,s,s,c))return 3;const char*r=(const char*)glGetString(GL_RENDERER);if(!r||!strstr(r,"llvmpipe"))return 4;glClearColor(1,0,0,1);glClear(GL_COLOR_BUFFER_BIT);unsigned char rgb[3];glReadPixels(0,0,1,1,GL_RGB,GL_UNSIGNED_BYTE,rgb);if(rgb[0]!=255||rgb[1]!=0||rgb[2]!=0)return 5;puts(r);eglTerminate(d);return 0;}
''')
    app=WORK/'new_egl';egl=find_library('EGL');gl=find_library('GL');execute(['gcc',source,'-I',INSTALL/'include',egl,gl,'-Wl,-rpath,'+str(egl.parent),'-o',app],env=e);assert str(INSTALL) in execute(['ldd',app],env=e).stdout.decode();return execute([app],env=e).stdout.decode()


def gdal():
    result=pkg_consumer('gdal_sdk',r'''
#include <gdal.h>
#include <cpl_conv.h>
#include <stdio.h>
int main(){GDALAllRegister();GDALDriverH drv=GDALGetDriverByName("GTiff");if(!drv)return 1;GDALDatasetH d=GDALCreate(drv,"new.tif",10,8,1,GDT_Byte,0);if(!d)return 2;double gt[6]={120,.1,0,30,0,-.1};if(GDALSetGeoTransform(d,gt)!=CE_None)return 3;unsigned char a[80];for(int i=0;i<80;i++)a[i]=i;if(GDALRasterIO(GDALGetRasterBand(d,1),GF_Write,0,0,10,8,a,10,8,GDT_Byte,0,0)!=CE_None)return 4;GDALClose(d);d=GDALOpen("new.tif",GA_ReadOnly);unsigned char b[80];if(!d||GDALRasterIO(GDALGetRasterBand(d,1),GF_Read,0,0,10,8,b,10,8,GDT_Byte,0,0)!=CE_None)return 5;for(int i=0;i<80;i++)if(a[i]!=b[i])return 6;double g[6];if(GDALGetGeoTransform(d,g)!=CE_None||g[0]!=120||g[5]!=-.1)return 7;GDALClose(d);puts("new GDAL raster write/read/geotransform passed");return 0;}
''',['gdal']);info=json.loads(execute([binary('gdalinfo'),'-json','new.tif'],env=env()).stdout);assert info['size']==[10,8];return result


def vtk():
    (WORK/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(NewVTK CXX)\nfind_package(VTK REQUIRED COMPONENTS CommonCore CommonDataModel FiltersCore FiltersSources IOLegacy)\nadd_executable(new_vtk new_vtk.cpp)\ntarget_link_libraries(new_vtk PRIVATE ${VTK_LIBRARIES})\nvtk_module_autoinit(TARGETS new_vtk MODULES ${VTK_LIBRARIES})\n')
    (WORK/'new_vtk.cpp').write_text(r'''
#include <vtkNew.h>
#include <vtkSphereSource.h>
#include <vtkPolyDataWriter.h>
#include <vtkPolyDataReader.h>
#include <vtkPolyData.h>
#include <iostream>
int main(){vtkNew<vtkSphereSource>s;s->SetThetaResolution(12);s->SetPhiResolution(10);s->Update();auto n=s->GetOutput()->GetNumberOfPoints();if(n<=50)return 1;vtkNew<vtkPolyDataWriter>w;w->SetFileName("new.vtk");w->SetInputConnection(s->GetOutputPort());if(!w->Write())return 2;vtkNew<vtkPolyDataReader>r;r->SetFileName("new.vtk");r->Update();if(r->GetOutput()->GetNumberOfPoints()!=n)return 3;std::cout<<"new VTK geometry/IO consumer passed "<<n<<"\n";return 0;}
''');execute(['cmake','-S',WORK,'-B',WORK/'build','-DCMAKE_PREFIX_PATH='+str(INSTALL)]);execute(['cmake','--build',WORK/'build','-j2']);app=WORK/'build/new_vtk';assert str(INSTALL) in execute(['ldd',app],env=env()).stdout.decode();return execute([app],env=env()).stdout.decode()

CONSUMERS={'BUILDv1-C%02d'%n:fn for n,fn in enumerate([ffmpeg,gstreamer,imagemagick,vips,opencv,blender,godot,mesa,gdal,vtk],1)}
