# 动态照片：MiniMax H3 单图执行契约

新产品使用 `dynamic_video` 工作流身份 `travel.minimax-h3.dynamic-photo.i2v@1.0.0`。它沿用已经安装的本地 MiniMax H3 图和 ComfyClient，不更改旧 `video`/memory 的 1024×576、16:9、cover/contain、拼接及音频语义。新执行器 `DynamicPhotoH3` 由后续 integration 节点接入既有单 worker；执行期间使用同一个 `ModelController.use("video")`，本模块不启动另一套调度器。

画布按已安装 H3 节点源码核对的 32 像素格、最大 768×1344 像素挑选：先最小化相对比例误差，再在同等误差下取较大面积。冻结记录原宽高、模型画布宽高、等比缩放后内容宽高、补边像素、相对比例误差和策略版本。误差超过 2% 时明确拒绝；输入始终等比 contain，不裁切、不拉伸。画布候选当前保守限定单边 256–1344 像素；真实 H3 对这些尺寸的可运行性须在 real-validation 节点证明。对于约 5 秒，工作流请求 124 帧、24 fps，理论时长 124/24≈5.17 秒，实际以视频探针为准。

执行意图在发送图片前持久化：所选 `photoId`、输入 hash、画布、工作流快照及 hash、seed、AI 运动提示词/版本和固定 UUID prompt ID。提交状态为 `prepared → submitting → submitted`，`submitting` 在任何出站调用前写盘。崩溃恢复先查询同一 prompt ID 的队列/历史；若已进入 `submitting` 但队列/历史查不到，明确报 `H3_SUBMISSION_UNKNOWN` 并停止，不自动重投。后续显式重试也必须先解决这个未知状态。成功下载的 H3 MP4 经 FFmpeg 转为 H.264/yuv420p 并移除所有音轨，抽取 JPEG 封面。`ffprobe` 检查编码、无音轨、画布尺寸、实际帧率、帧数和时长；`ffmpeg -xerror -f null` 完整解码全部视频帧。检查成功后才把文件 hash、尺寸、帧数、实际时长、封面 hash 及工作流/seed/prompt 身份写入任务结果。重复调用复用有效终态；失败保留静态来源和所选照片，不自动选下一张。显式有限重试由 integration 节点提供。

本阶段针对性测试用本地图像与 Comfy 替身验证比例映射、上传画布、工作流隔离、意图持久化、控制器使用和失败保留；同时运行旧 workflow_versions 回归。Mac 隔离环境没有 `ffmpeg`/`ffprobe`，因此后处理代码尚未在本机执行真实小片；CPU FFmpeg 小片和真实 H3 产物验证需在 Spark 环境完成，不能把替身结果当成 c04 的模型证据。
