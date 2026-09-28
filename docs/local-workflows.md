# 本地 Qwen / H3 工作流

## 版本与文件

Spark 只读核对日：2026-09-28。API 运行目录当时为 `24aae844e252fe7cd8606a8f25ede45b66990dc0`。模型服务在核对时均停止，以下节点与权重信息来自已安装源码和磁盘，并非本版生成实测。

| 用途 | ComfyUI 源码 / 版本 | 前端包 | API 图 | UI 图 |
| --- | --- | --- | --- | --- |
| Qwen-Image-2.1 | `4ef23c34` / `0.37.0` | `1.53.6` | `workflows/qwen-image-2.1-edit-api.json` | `workflows/qwen-image-2.1-edit-ui.json` |
| MiniMax H3 | `e80c1570` / `0.34.0` | `1.51.9` | `workflows/minimax-h3-i2v-api.json` | `workflows/minimax-h3-i2v-ui.json` |

`workflows/model-manifest.json` 固定模型文件名、当时字节数、节点来源、引擎提交和参数 schema。H3 另有 `ComfyUI_MiniMaxH3_Director@7de4a952` 与 `minimax-h3-hybrid-cond@a1f20e01`。权重哈希、运行环境节点注册及 UI 导入仍须在真实探针阶段复核。

## 尺寸、时长和 seed

- Qwen 安装源码 `comfy_extras/nodes_qwen.py:111-167` 的 `TextEncodeQwenImage21` 仅暴露 `resolution`（0–4096、步长 32），首张参考图比例决定 latent 宽高，不存在可直接指定的 `width` / `height` 输入。本版固定 `resolution=1024`。手帐请求显式传 `parameters={"aspect_ratio":"3:2"}` 时，适配器将完整原图等比放进白色 `1536×1024` 画布；按该节点公式，目标 latent 为 `1248×832`（3:2）。旧重绘调用无参数时仍用 `source` 比例。真实输出比例和主体效果待 Qwen 探针确认。
- H3 安装源码 `comfy_extras/nodes_minimax_h3.py:114-150` 接受 `width` / `height`（32 的倍数）和 `length`（17k+5 帧网格）；首帧会被拉伸到画布。历史 `1.0.0` 快照将完整原图等比放进 `1024×576` 白色画布。真实 H3 首镜头已证明这会产生可见白边；新 `1.1.0` 输入策略见末节。controller 的 50 GiB 预算未调整。
- H3 默认 124 帧、24 fps，即约 5.17 秒；`frames` 仅接受 124–362 范围内的 17 步长值。H3 `RandomNoise.noise_seed` 与 Qwen `KSampler.seed` 均接任务 seed（0 到 2^64-1）。API 图不把静态照片缩放当作视频生成。

## 快照与提交契约

`ComfyClient.freeze_workflow()` 返回可写入任务 JSON 的深拷贝，含 `schema_version`、`workflow_id`、`workflow_version`、`workflow_hash`、`snapshot_hash`、`api_graph`、`engine`、`custom_nodes`、`model_nodes`、`parameter_schema`、`input_policy`。提交任务时由 runtime 保存该快照及参数；执行时调用 `queue(image, prompt, seed, workflow_snapshot=saved_snapshot, parameters=saved_parameters)`。有快照时适配器不读当前默认工作流或 manifest；参数默认值、范围和白名单均来自快照内 schema。历史 H3 `1.0.0` 固定 `contain-white-v1`，新 H3 `1.1.0` 固定 `contain-or-cover-v2`；未知参数、非法 seed、变更过的快照在上传图片前拒绝。旧三位置调用仍可用。

API JSON 供服务端提交；UI JSON 使用 ComfyUI 的画布节点和连线格式，供内部界面导入、查看及调参。UI 图的图片名、提示词和 seed 是空白/零占位，导入后需选择私有测试图片；UI 编辑结果应先导出 API 格式，完成 schema、尺寸和真实探针审查后再递增 `workflow_version` 与 manifest。不能只替换文件而沿用旧版本号。

UI 的 KSampler 与 RandomNoise 在 seed 后保存 `control_after_generate=fixed` 控件；这是已安装节点声明的独立控件值，不能省略，否则后续采样参数会错位。真实 UI 导入仍须按下文验证。

### 提交身份和恢复

两套已安装 ComfyUI 的 `server.py:post_prompt` 均接受调用方提供的规范 UUID `prompt_id`。适配器 `queue(..., prompt_id=saved_id)` 在上传前校验格式，提交该 ID，并检查响应编号一致。队列调用者必须先持久化此 ID，再发送请求；遇到响应丢失或 API 重启，先查相同 ID 的 history/queue。ComfyUI 本身不保证相同 ID 重复 POST 去重，因此不得把此字段视为自动幂等功能。持续无法确认时明确失败，人工重试另存新 ID。

[ComfyUI 官方 APP mode 文档](https://docs.comfy.org/interface/app-mode) 指出其起始前端版本为 `1.41.13`。现装的 `1.53.6` 和 `1.51.9` 均满足**版本下限**；本轮未启动服务或实测导入及 APP mode，不能宣称实际可用。内部本地 APP 使用不依赖云分享；云分享 URL 不在本任务范围。

## 后续真实验证

在 contract 与本准备节点集成后，经共享 controller 单 worker 分别运行 Qwen 3:2 图片和 H3 16:9 动态单镜头。记录 ComfyUI `/object_info`、UI 导入/APP mode、实际输出宽高和编码、seed 请求图、耗时、峰值内存及产物。若 `1024×576` 超出预算或节点实际不接受，先更新计划和版本，不将源码支持等同生成通过。

## 2026-09-28 实测追加

Spark API 验证分支 `codex/m01-validation-20260928` 部署 `37ecdc75`。主会话通过正式 selected-photos 和 original 接口独立复核了四张公共照片的批次与哈希。测试集合跨不同日期，不代表同一次真实旅行。

- Qwen 作业 `1c800b6b-2dfe-45c6-93a2-4166c1a22ad6` 成功，实际输出 **1248×832，严格 3:2**。Comfy history 中 seed 为 `2026092801`；作业运行约 40.38 秒。原始引擎输出为 PNG，MediaStore 交付规范化 JPEG。主审看到了秋景水彩重绘、同场景树/山/云贴纸与纸底。[收据](generated-evidence/m01/qwen-probe.json)和[实际样图](generated-evidence/m01/qwen-watercolor-probe.jpg)仅作为公共基础探针，五风格业务验收仍由 M02 完成。
- 实际 Qwen 前端导入 UI 图后，主会话核对了 seed、25 steps、cfg=1、1024 resolution 及首张图连线；导出 API 参数一致。APP 构建器成功配置图片、prompt、seed 输入及 SaveImage 输出，并展示表单预览。导出的 `workflows/qwen-image-2.1-edit-app.json` 可用于内部调参；[预览截图](generated-evidence/m01/qwen-app-preview.png)为实际运行界面。没有从 UI 另行提交推理。
- 前端提示 workflow-templates `0.11.54` 低于建议的 `0.11.70`。自定义图导入和 APP 构建已运行；未据此升级环境，也不保证模板库全部兼容。
- 七份实际权重的 SHA-256 见[模型哈希](validation-assets/m01-model-hashes.json)。Qwen 此次未采集全程峰值，生成后的可用内存不能冒充峰值。
- H3 首次探针的引擎已生成 1024×576 / 124 帧 / 24 fps 单镜头；完整产物和恢复证据由主会话另行审查，服务 ready 仍不等于生成通过。

## H3 1.1.0 输入构图策略与单镜头实测

`model-manifest.json` 的 H3 `workflow_version` 升为 `1.1.0`，`input_policy=contain-or-cover-v2`，参数 schema 新增 `fit_mode: contain|cover`，默认 `cover`。`cover` 在服务端以居中裁切把规范化 original 铺满 `1024×576`，避免把人工白边送入 H3；显式 `contain` 仍完整保留原构图并使用白底留边。两种模式均保持画布严格 16:9、124 帧与 24 fps 默认值、任务 seed，以及 selected-only original 资格。非法 `fit_mode` 在上传前拒绝。

首个公开测试原图为 `1920×1227`；旧 `contain` 缩为 `901×576`，左右约留 61/62 像素。新 `cover` 需要截到约 `1920×1080`，上下合计损失 147 像素，约占原图高度 **12%**。顶部地貌、底部栈道或其他照片边缘的人物和地标可能被裁掉；需要完整构图时明确选择 `contain`。裁切是有损取舍，不能写作无损或保证主体永不受损。

历史排队任务的 `1.0.0` 快照仍固定 `contain-white-v1`，不读取新版 manifest 的 `fit_mode` 默认值。新旧 API 节点图本身可以相同，但版本号、参数 schema、输入策略与 `snapshot_hash` 不同；旧图哈希相同不意味着旧任务自动采用新构图。内部 ComfyUI UI/APP 直接上传照片运行图时**不会**经过业务适配器的 cover/contain 预处理；只有正式 API 提交路径会应用这个策略。UI 调参若要复现实效，须先准备同样的输入画布并记录模式，不能把 UI 图称为自动 cover。

经正式 selected-only API 和共享 controller 提交的 `1.1.0` / `cover` 单镜头作业 `ad2e7823-3ecb-4de0-b1d4-e15312ef6da5` 已成功，HTTP 200 成片为 **1024×576、24 fps、5.216 秒**，完整 CPU 解码通过。[实测收据](generated-evidence/m01/framing-real-probe.json)和[成片](generated-evidence/m01/framing-cover-probe.mp4)记录了原图、冻结快照、输出哈希及旧任务不变证据。首中尾与 1–4 秒画面未见旧版左右人工白边；温泉与栈道仍可见，蒸汽和镜头有动态，但上下边缘确按上述比例裁去。AAC 音轨非静音，内容及授权来源未确认。

运行中读取 Comfy `/history/{promptId}` 时记录尚未就绪，作业完成后 controller 已停止 H3 服务，故本次**未取得在线 history 图**。成片嵌入元数据含 1024×576、124 帧、24 fps、seed `2026092802`，仅作为辅助证据，不冒充在线 history。此单镜头也不代表 M03 完整成片或 M02 五风格验收；主审仍需独立评估 criterion。
