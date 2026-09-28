# 本地 Qwen / H3 工作流（M01 准备阶段）

## 版本与文件

Spark 只读核对日：2026-09-28。API 运行目录当时为 `24aae844e252fe7cd8606a8f25ede45b66990dc0`。模型服务在核对时均停止，以下节点与权重信息来自已安装源码和磁盘，并非本版生成实测。

| 用途 | ComfyUI 源码 / 版本 | 前端包 | API 图 | UI 图 |
| --- | --- | --- | --- | --- |
| Qwen-Image-2.1 | `4ef23c34` / `0.37.0` | `1.53.6` | `workflows/qwen-image-2.1-edit-api.json` | `workflows/qwen-image-2.1-edit-ui.json` |
| MiniMax H3 | `e80c1570` / `0.34.0` | `1.51.9` | `workflows/minimax-h3-i2v-api.json` | `workflows/minimax-h3-i2v-ui.json` |

`workflows/model-manifest.json` 固定模型文件名、当时字节数、节点来源、引擎提交和参数 schema。H3 另有 `ComfyUI_MiniMaxH3_Director@7de4a952` 与 `minimax-h3-hybrid-cond@a1f20e01`。权重哈希、运行环境节点注册及 UI 导入仍须在真实探针阶段复核。

## 尺寸、时长和 seed

- Qwen 安装源码 `comfy_extras/nodes_qwen.py:111-167` 的 `TextEncodeQwenImage21` 仅暴露 `resolution`（0–4096、步长 32），首张参考图比例决定 latent 宽高，不存在可直接指定的 `width` / `height` 输入。本版固定 `resolution=1024`。手帐请求显式传 `parameters={"aspect_ratio":"3:2"}` 时，适配器将完整原图等比放进白色 `1536×1024` 画布；按该节点公式，目标 latent 为 `1248×832`（3:2）。旧重绘调用无参数时仍用 `source` 比例。真实输出比例和主体效果待 Qwen 探针确认。
- H3 安装源码 `comfy_extras/nodes_minimax_h3.py:114-150` 接受 `width` / `height`（32 的倍数）和 `length`（17k+5 帧网格）；首帧会被拉伸到画布。本版先将完整原图等比放进 `1024×576` 白色画布，再把同尺寸传节点，避免额外裁掉主体。这个画布是源码支持的**待探针候选**，其内存峰值及真实视频比例尚未验证，不调整 controller 的 50 GiB 预算。
- H3 默认 124 帧、24 fps，即约 5.17 秒；`frames` 仅接受 124–362 范围内的 17 步长值。H3 `RandomNoise.noise_seed` 与 Qwen `KSampler.seed` 均接任务 seed（0 到 2^64-1）。API 图不把静态照片缩放当作视频生成。

## 快照与提交契约

`ComfyClient.freeze_workflow()` 返回可写入任务 JSON 的深拷贝，含 `schema_version`、`workflow_id`、`workflow_version`、`workflow_hash`、`snapshot_hash`、`api_graph`、`engine`、`custom_nodes`、`model_nodes`、`parameter_schema`、`input_policy`。提交任务时由 runtime 保存该快照及参数；本准备节点未修改 `jobs.py`。执行时调用 `queue(image, prompt, seed, workflow_snapshot=saved_snapshot, parameters=saved_parameters)`。有快照时适配器不读当前默认工作流或 manifest；参数默认值、范围和白名单均来自快照内 schema。输入留白策略也由快照固定为 `contain-white-v1`。未知参数、非法 seed、变更过的快照在上传图片前拒绝。旧三位置调用仍可用。

API JSON 供服务端提交；UI JSON 使用 ComfyUI 的画布节点和连线格式，供内部界面导入、查看及调参。UI 图的图片名、提示词和 seed 是空白/零占位，导入后需选择私有测试图片；UI 编辑结果应先导出 API 格式，完成 schema、尺寸和真实探针审查后再递增 `workflow_version` 与 manifest。不能只替换文件而沿用旧版本号。

[ComfyUI 官方 APP mode 文档](https://docs.comfy.org/interface/app-mode) 指出其起始前端版本为 `1.41.13`。现装的 `1.53.6` 和 `1.51.9` 均满足**版本下限**；本轮未启动服务或实测导入及 APP mode，不能宣称实际可用。内部本地 APP 使用不依赖云分享；云分享 URL 不在本任务范围。

## 后续真实验证

在 contract 与本准备节点集成后，经共享 controller 单 worker 分别运行 Qwen 3:2 图片和 H3 16:9 动态单镜头。记录 ComfyUI `/object_info`、UI 导入/APP mode、实际输出宽高和编码、seed 请求图、耗时、峰值内存及产物。若 `1024×576` 超出预算或节点实际不接受，先更新计划和版本，不将源码支持等同生成通过。
