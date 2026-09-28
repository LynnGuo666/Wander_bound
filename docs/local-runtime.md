# M01 本地生成运行时约定

本文件描述现有私有 `redraw` 与 `memories` 执行路径；`/api/media/generation-jobs` 的 scrapbook、storyboard、video 仍仅生成 `prepared` DTO，不会调度模型。

## 提交与冻结

`POST /api/media/photos/{photoId}/redraw` 接受 `prompt`、可选 `seed`、可选 `parameters`。图片参数目前仅支持 `aspect_ratio: "source" | "3:2"`，默认 `source`。`POST /api/media/memories` 接受 `tripId`、`photoIds`、`title`、可选 `seed`、可选 `parameters`。视频参数为 `aspect_ratio: "16:9"`、`frames`（124–362，步长 17）、`fps: 24`。未指定的参数由当前工作流 schema 产生并全部持久化；未提供 seed 时服务端产生 64 位无符号整数。响应返回 `id`、`status`、`backend`、`seed`、`parameters`；非法参数返回结构化 `WORKFLOW_PARAMETERS_INVALID` 400。

提交前先从服务端已提交选优清单冻结 `selectionSnapshot`，逐张校验并哈希规范化 JPEG original。随后调用 adapter `freeze_workflow()`，把 `workflowSnapshot`（API 图、版本、哈希、模型及参数 schema）、归一化参数和 seed 深拷贝进 job JSON。视频还保存每个输入镜头的确定 seed：`(job.seed + index) mod 2^64`。队列执行和重启恢复只能使用 job 中的快照与参数；当前工作流文件的后续替换不会改变已提交任务。

无 `selectionSnapshot`、无 `workflowSnapshot` 或快照与任务参数不一致的旧排队任务在申请模型前失败，分别给出 `SNAPSHOT_INVALID` 或 `WORKFLOW_SNAPSHOT_INVALID`。保留旧任务供调查，不能用当前选优或当前工作流隐式补齐。原图不存在、非 JPEG 或内容哈希变化也会失败，不会改读 develop/AI 变体。

## 队列、恢复和失败

运行时通过 `ModelController.use(image|video)` 共享单工作者模型调度。每次向 ComfyUI 提交前，先将规范 UUID `promptId` 和 `submissionState: intent_recorded` 写入 job；adapter 用同一 ID 向 `/prompt` 提交并校验响应。响应丢失时状态记为 `unknown`，只用持久 ID 查询 history 和 queue。API 重启后已有 `promptId` 的任务也只对账，不再次提交。队列内任务继续等待，历史完成则下载，明确失败立即终止，连续三次缺失或服务不可达即失败，不会反复重提交。执行轮询最多 360 次，每次间隔 5 秒。模型资源申请连续失败最多三次，每次间隔 30 秒，随后 `RESOURCE_RETRY_EXHAUSTED`。显式 retry 总 attempt 最多三次，失败 prompt 才分配新 UUID；已完成但尚未保存的产物保留原 UUID 供重取，并保留冻结快照、参数、seed 与已完成镜头。

图片已保存的 `ai-{jobId}` 变体在恢复时直接确认完成。视频每个镜头先写 `.pending.mp4`，再原子替换为 `{index}.mp4`，保存 `done`。已完成且文件存在的镜头不会再次生成；已有 prompt 而镜头文件缺失时会对账历史并重下载。所有镜头完成后 ffmpeg 合成为 `memory.pending.mp4`，再原子替换 `memory.mp4`；最终文件存在时重启可直接确认完成。不会自动重试 ComfyUI 明确失败的 prompt；需要调用相应 retry 路由，未完成镜头才会重新排队。

## 验证边界

准备阶段用合成 JPEG、假 Comfy 响应及假 ffmpeg 测试队列语义；这些测试不能证明真实模型产物。以下真实恢复观察只覆盖已记录的时间窗口，镜头质量和完整 c03 验收仍须另查。

## Spark 真实恢复检查（2026-09-28，进行中）

主会话提交的 selected 原图 H3 job `90981311-bf42-47f5-b189-b7fcc62c5202` 于 20:26:54 +08 开始，镜头 prompt UUID 为 `4e38017b-4ff3-485c-9009-4063c1bcdc4d`。本轮在它仍处于 Comfy `queue_running` 时，仅执行一次 `systemctl --user restart travel-agent.service`：API PID `1154560 → 1155843`。重启前、立即恢复及 5 秒后，job 均为 `running/attempt=1/resourceRetries=2`，镜头 prompt 与队列 running ID 相同，pending 为空；重启后 authenticated memory GET 为 HTTP 200，控制器仍显示 `activeModel=video`。原始脱敏读数分别见 [重启观察](generated-evidence/m01/runtime-h3-restart.json)与 [API 回读](generated-evidence/m01/runtime-api-after-restart.json)。

主会话在 H3 运行期间提交另一 Qwen job `92e48610-b124-46c2-a4bd-07a4a31ad2ec`。20:36:20 +08 的 [并发读数](generated-evidence/m01/runtime-concurrency-observation.json)显示 H3 仍运行，Qwen `queued/startedAt=null`，API queue 为一条 video 加一条 image，Comfy queue 只有原 H3 prompt。H3 完成后的 Qwen 启动顺序、最终 MP4 与下载哈希尚待追踪；这些中间读数不构成 c03 完整通过。

真实 H3 在两次资源等待后进入 `running` 时，旧 busy `error` 文本仍在 job 中。本地后续提交 `fa9c197` 清正常运行/成功状态下的当前 `error/errorCode`，保留历史 `resourceRetries`；全量 pyserver 测试 64 passed。Spark 当前任务仍使用已部署 `37ecdc75`，本轮未部署这项修复。

### 镜头成功后的合成故障与本地修复

H3 引擎原 prompt 实际生成并保存 `0.mp4`，大小 1,087,931 字节、SHA-256 `30c75a8a287b295fcaa925ac6adb477541a0cf1f0bb36403cd117a19a7dff773`；ffprobe 为 H.264 `1024×576`、24 fps、5.167 秒，带 AAC 音轨。job 记录 `completedClips=1`、`done=true`，但最终 `failed/JOB_FAILED`，原因是 concat 列表写入 `data/media/jobs/.../0.mp4`，FFmpeg 又相对 `clips.txt` 所在目录解析，使路径重复。完整脱敏元数据见 [H3 结果](generated-evidence/m01/runtime-h3-outcome.json)。主会话排队的 Qwen job 在 20:39:50 +08 才开始、20:40:25 成功；[交接结果](generated-evidence/m01/runtime-handoff-outcome.json)同时保留两个任务的终态及哈希，观察时 API queue 为 0。H3 最终 `memory.mp4` 尚不存在，不能把镜头成功称作成片成功。

本地修复将 concat 条目写成同目录 basename `file '0.mp4'`；已有图片变体及所有已存在有效镜头可不加载模型直接恢复，镜头与最终 MP4 在复用/发布前需经 ffprobe 检查非空、可解码、16:9 和正时长。对于坏文件，不以 `done` 标志冒充完成。Spark `/tmp` 中用合成蓝色 160×90、24 fps、0.5 秒小片段运行了真实 FFmpeg 回归：旧路径返回 254 且出现重复目录，新 basename 成功并由 ffprobe 确认输出；见 [FFmpeg 回归](generated-evidence/m01/runtime-ffmpeg-regression.json)。本地 pyserver 全量测试 **68 passed**。修复提交尚未部署，原 H3 job 的正式 retry 与最终 MP4 下载仍待主会话部署后验证。
