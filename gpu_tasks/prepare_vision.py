import concurrent.futures
import json
import os
from pathlib import Path
import zipfile
from PIL import Image
from assets import ROOT,ASSETS,fetch,digest
from prepare_graphs import manifest
from specify_ready import freeze

def pretrained_weights():
    import torchvision.models as m
    from torchvision.models.detection import RetinaNet_ResNet50_FPN_Weights,MaskRCNN_ResNet50_FPN_Weights
    specs={'resnet50':m.ResNet50_Weights.DEFAULT,'retinanet':RetinaNet_ResNet50_FPN_Weights.DEFAULT,'maskrcnn':MaskRCNN_ResNet50_FPN_Weights.DEFAULT}
    for name,weights in specs.items():
        url=weights.url;p=fetch(url,ASSETS/'models/torchvision'/url.rsplit('/',1)[-1],max_bytes=300*2**20)
        (p.parent/(name+'.json')).write_text(json.dumps({'name':name,'url':url,'sha256':digest(p),'container_path':'/models/torchvision/'+p.name,'categories':weights.meta['categories']},indent=2)+'\n')
        print('TV_WEIGHTS',name,flush=True)

def coco():
    source=fetch('https://s3.amazonaws.com/images.cocodataset.org/annotations/annotations_trainval2017.zip',ASSETS/'vision/annotations_trainval2017.zip',max_bytes=300*2**20)
    with zipfile.ZipFile(source) as z:annotations=json.loads(z.read('annotations/instances_val2017.json'))
    images=sorted(annotations['images'],key=lambda x:x['id'])[:16]
    image_ids={x['id'] for x in images};objects=[x for x in annotations['annotations'] if x['image_id'] in image_ids]
    image_dir=ASSETS/'vision/coco_val16';image_dir.mkdir(parents=True,exist_ok=True)
    def get_image(info):
        url='https://s3.amazonaws.com/images.cocodataset.org/val2017/'+info['file_name']
        p=fetch(url,image_dir/info['file_name'],max_bytes=8*2**20)
        with Image.open(p) as im:assert im.size==(info['width'],info['height'])
        return p
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(get_image,images))
    for tid in ['GPUv1-B02','GPUv1-B03']:
        task=ROOT/'tasks'/tid;(task/'input/images').mkdir(parents=True,exist_ok=True);(task/'oracle').mkdir(exist_ok=True)
        for info in images:
            target=task/'input/images'/info['file_name']
            if not target.exists():os.link(image_dir/info['file_name'],target)
        (task/'input/images.json').write_text(json.dumps(images,indent=2)+'\n')
        (task/'oracle/annotations.json').write_text(json.dumps({'images':images,'annotations':objects,'categories':annotations['categories']}))
        if tid.endswith('B03'):
            training_ids={x['id'] for x in images[:12]}
            training={'images':images[:12],'annotations':[x for x in objects if x['image_id'] in training_ids],'categories':annotations['categories']}
            (task/'input/train_annotations.json').write_text(json.dumps(training))
        manifest(tid,{'dataset':'COCO val2017 native first 16 numeric image IDs','source_annotations':'https://cocodataset.org/','annotation_archive_sha256':digest(source),'image_sha256':{x['file_name']:digest(image_dir/x['file_name']) for x in images},'deviations':['16 genuine COCO images; B02 category dataset differs from OpenImages, B03 debug train12/validation4 partition drawn from source val2017, not formal training/validation']})
    freeze('GPUv1-B02','建立可重载查询的真实目标框目录','''用 /models/torchvision/retinanet.json 指定的官方 TorchVision RetinaNet ResNet50-FPN 权重在 CUDA 上检测 input/images.json 清单的 16 张完整 COCO 图像。min_size=320、max_size=640、score threshold=0.25，保留 COCO category ID，不重新训练。入口 python solution/main.py detect --input input --output output；输出 detections.json（每图 image_id/file_name/original_size 和全部 boxes/labels/scores；即使无检测也有记录）、catalog.json（类别映射、图像到结果索引、模型/参数绑定）、run.json。另实现 python solution/main.py query --catalog output/catalog.json --image-id ID，标准输出该图检测 JSON，不依赖原始图像。独立用冻结模型重算 boxes/labels/scores 与排序，检查原图坐标、所有图覆盖、score threshold、跨进程目录查询与 CUDA forward。真实 COCO mAP 单独报告；debug 不等于 OpenImages 全量通过。''')
    freeze('GPUv1-B03','适配实例分割模型并导出真实对象轮廓','''用 TorchVision Mask R-CNN ResNet50-FPN，初始化权重由 /models/torchvision/maskrcnn.json 指定。input/train_annotations.json 是 12 张真实图的原始 COCO instance boxes/polygons，images.json 共 16 张；余下 4 张只有图像，没有标签。用 pycocotools 解码真实 mask，在 CUDA 上至少对全部 12 个训练图各执行一次有效优化器更新；min_size=320/max_size=640，类别使用原始 COCO 91-ID 约定。
入口 python solution/main.py train --input input --output output；python solution/main.py predict --checkpoint output/checkpoint.pt --input input --output output/reloaded。保存 checkpoint.pt（完整标准 TorchVision state_dict、模型配置、optimizer/step/RNG），每幅完整图的预测 boxes/labels/scores/mask RLE 到 instances.json，并输出 contours.json（从预测二值 mask 提取原图坐标外轮廓），run.json。推理 score threshold=0.25、mask threshold=0.5。独立检查权重变化、真实 CUDA mask loss/backward、标准重载一致、mask/box/轮廓一致和覆盖；未训练初始化权重、不使用 segmentation 标注、二维 boxes 冒充 masks 均失败。小样本质量只报告。''')
    print('B02/B03 INPUT READY',flush=True)

if __name__=='__main__':pretrained_weights();coco()
