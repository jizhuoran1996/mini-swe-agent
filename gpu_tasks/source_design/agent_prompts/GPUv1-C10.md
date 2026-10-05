# GPUv1-C10 · Agent任务提示模板

Builder在实例化时补充可见输入路径、冻结配置、允许的工具和设备预算。初始任务与后续请求分阶段交付；不把本文件中未来请求提前用于模拟再次访问。验证器的隐藏数据不出现在任务环境。

## 初始任务

根据物体参考图批量制作带材质的三维资产，要求文件可重新载入、材质和纹理有效，并能在指定视角与灯光下渲染，交付可供三维场景使用的资产目录。

### 来源和工作范围

Tencent Hunyuan3D-2.1 shape + paint pipeline / Google Scanned Objects 1,030-object collection

### 交付要求

- assets/<object_id>/scene.glb 或等价完整 mesh/material 包
- renders/<object_id>/
- asset-catalog.jsonl
- camera-and-generation-config.json

### 必须完成的工作

- 从输入图生成真实几何，再执行纹理/PBR 管线
- 保存独立 mesh/材质资产并重新载入
- 按请求相机和灯光渲染检查图，建立物体 ID 到资产的目录

请在分配的环境中真实完成计算并保存可重载的产物。使用实例清单规定的输入ID、模型和工作量；若出现错误，保留失败项与实际状态。不要用外部模型API、预先生成的答案或重复数据替代规定的GPU工作。允许使用官方CLI和现有工具，无需刻意拆成多次调用。

## 后续请求（依实际依赖单独发出）

把指定已交付物体组成一个小场景，在新的相机/光照设置下渲染；必须复用实际生成几何和材质，不使用二维贴片替代。

如果后续请求包含新输入，builder在采集前将完整输入集合分为互斥的initial和continuation子集；重复访问另行标记。
