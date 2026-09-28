# 历史研究记录

本文件记录旧 Node 媒体服务的实验过程。现行实现位于 `pyserver/media/`，架构见 `MEDIA_ARCHITECTURE.md`；旧代码保存在 Git 标签 `archive/node-server`。

# 旅行照片编辑模型与媒体模块化方案

调研日期：2026-09-28。本轮资料核对结束时间：2026-09-28 06:43 CST。这里区分“模型权重能否在 Spark 上加载”和“已在本队 Spark 上验证”。MiniMax H3 视频链路已经过本队节点验证。Qwen-Image-2.1 的隔离 ComfyUI 服务已启动，三份权重通过 SHA-256 校验，并完成合成风景图的中文重绘及已鉴权媒体 API 全链路测试。其余静态图像编辑模型仍为候选。

## 选型结论

DGX Spark 使用 ARM64/Blackwell、128 GB CPU/GPU 共享内存。容量允许试验较大的图像模型，但不能据此推断延迟或与现有 H3 同时常驻的可行性。2026-09-28 通过只读 SSH 核实本队节点为 `aarch64`，`minimax-h3-comfy.service` 正在运行，回环地址的 ComfyUI `/system_stats` 报告版本 `0.34.0`。该服务早于 Qwen-Image-2.1 的发布，须在隔离环境升级并验证新工作流，不能直接覆盖现有 H3 环境。测试时串行调度图像编辑和 H3 视频生成，记录每次峰值内存、耗时与结果。

| 候选 | 日期与用途 | 权重许可 | 接入优先级 |
| --- | --- | --- | --- |
| [Qwen-Image-2.1](https://github.com/QwenLM/Qwen-Image-2.1) | 2026-09-20；7B 图像生成组件，单图／多参考图自然语言编辑，原生 2K、透明图；官方 ComfyUI 工作流 | [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)：研究／非商业；商业用途需另获许可。GitHub 代码的 Apache-2.0 不覆盖权重 | **本项目研究用途首选**；先验证 Spark 推理，再接入媒体 API |
| [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | 2025-12；中文指令、多参考图、文字和风格编辑 | Apache-2.0 | 对照模型；需测 Spark 吞吐和场景保持 |
| [FLUX.2 Klein 4B](https://github.com/black-forest-labs/flux2) | 2026-01；快速预览、单图及多参考图编辑 | 4B 权重 Apache-2.0；同系列 9B／dev 为非商业许可 | 快速预览与备用编辑器 |
| [Step1X-Edit](https://github.com/stepfun-ai/Step1X-Edit) | 2025 起；自然语言图像编辑，包含评测与微调示例 | Apache-2.0 | 对照实验；需单独验证 ARM64 依赖 |

参考：[NVIDIA Spark 硬件与 ARM64 说明](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/overview.html)、[NVIDIA ComfyUI Spark playbook](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/comfy-ui/README.md)、[Qwen-Image-2.1 ComfyUI 说明](https://blog.comfy.org/p/qwen-image-21-in-comfyui-open-weight)。

**明信片需求**：输入旅行照片和自然语言，要求保留原地标与人物，生成一张风格化的底图；标题、日期和地点优先用确定性排版叠加，以便修改文字且避免模型拼写错误。允许风格参考图，但在界面上把结果标为“创意重绘”，与保真修图分开。

## 当前系统与目标边界

初始服务由 `server/media/images.mjs` 负责标准化、几个图像统计量和两种固定调色；`store.mjs` 保存 JPEG 及变体；`comfy.mjs` 连接 H3；`memories.mjs` 生成镜头并拼接；`routes.mjs` 包含鉴权、解析和业务路由。当前已抽出 Qwen 图像适配器和单进程持久化任务执行器，图像与 H3 在应用内顺序运行，状态查询不再驱动任务。iOS 上传前会把来源照片缩为 JPEG。场景识别、旅行关联、照片排序和跨进程资源锁仍未实现。

先定义同一份照片分析记录，再把处理器分开。推荐内部结构：

```text
server/media/
  api/                  鉴权、请求校验、照片／编辑／视频路由
  assets/               原图、预览、衍生版本、元数据及访问控制
  analysis/             场景识别、旅行关联、技术质量、观感、相似组
  corrections/          裁切、透视、曝光、白平衡、降噪等保真编辑
  creative/             提示词模板、图像编辑提供器、结果检查
  orchestration/        任务队列、状态、资源互斥、失败重试
  providers/            ComfyUI 协议、Qwen／FLUX 工作流、H3 工作流
  storytelling/         照片选择、时间线、字幕、地图与音乐
  rendering/            静态图层、FFmpeg 合成及成片校验
```

最小数据契约：`asset`（原始资源、授权旅程、拍摄日）、`analysis`（场景／主体／相关性／分项质量及模型版本）、`editRequest`（模式、原图 ID、自然语言、风格、受保护区域、seed）、`variant`（输出文件、来源链、处理器／模型／参数、生成标记）、`job`（排队／运行／完成／失败、进度、耗时）。所有版本必须可追溯到原图；修改原图质量或位深处理前，先核定私有存储、元数据去除和 iOS 上传约束。

推荐决策链：`识别场景与主体 → 判断本次旅程关联 → 分场景技术／美学评分 → 判断修复可能性 → 用户选择保真校正或创意重绘 → 生成并对比 → 用户确认入片`。评分保留各维度，不以单一总分自动删除有纪念价值的照片。

## 接入顺序与验证

1. **抽出媒体任务与提供器接口**：H3 与 Qwen 分别接入 `/upload/image → /prompt → /history → /view`，通过同一后台执行器顺序占用 Spark 推理资源。下一步可进一步合并重复的 ComfyUI 协议代码，并补跨进程资源锁。
2. **建立资源与版本模型**：原图、用于分析的预览、保真修图、创意重绘分别存储；保存模型、工作流版本、提示词和 seed。继续只通过已鉴权的媒体 API 提供文件。
3. **在 Spark 隔离环境先试 Qwen-Image-2.1，再用 FLUX.2 Klein 4B 对照**：先复制或新建 ComfyUI 运行环境，以不同回环端口启动并导入官方 2.1 工作流；保留现有 `0.34.0` H3 服务。选择同一批实拍的景点、城市夜景、人物和明信片提示词，比较主体／地标保持、中文字、质量、峰值内存和单张耗时。Qwen-Image-2.1 用于本项目已明确的非商业研究；若用途改变，重新核对权重许可。
4. **接入评价与确认**：同一张照片保留原图、保真版和创意版的并排预览；用人工盲选与固定测试集评价，不用模型自评分代替人看成片。
5. **再接故事编排**：把用户确认的版本送入视频时间线；明信片文字作为渲染图层，不烧进不可编辑的 AI 图像。

完成静态编辑可用性的判据：真实 iPhone 照片能在私网中完成“输入中文要求 → 排队 → 获取图像 → 对比原图 → 保存所选版本”；失败可重试；不影响现有 H3 视频接口；报告各模型在本队 Spark 上的实测耗时与内存。模型源文件、权重和 ComfyUI 节点都应固定版本与校验值。
