# M01 本地生成运行时约定

本文件描述现有私有 `redraw` 与 `memories` 执行路径；`/api/media/generation-jobs` 的 scrapbook、storyboard、video 仍仅生成 `prepared` DTO，不会调度模型。

## 提交与冻结

`POST /api/media/photos/{photoId}/redraw` 接受 `prompt`、可选 `seed`、可选 `parameters`。图片参数目前仅支持 `aspect_ratio: "source" | "3:2"`，默认 `source`。`POST /api/media/memories` 接受 `tripId`、`photoIds`、`title`、可选 `seed`、可选 `parameters`。视频参数为 `aspect_ratio: "16:9"`、`frames`（124–362，步长 17）、`fps: 24`。未指定的参数由当前工作流 schema 产生并全部持久化；未提供 seed 时服务端产生 64 位无符号整数。响应返回 `id`、`status`、`backend`、`seed`、`parameters`；非法参数返回结构化 `WORKFLOW_PARAMETERS_INVALID` 400。

提交前先从服务端已提交选优清单冻结 `selectionSnapshot`，逐张校验并哈希规范化 JPEG original。随后调用 adapter `freeze_workflow()`，把 `workflowSnapshot`（API 图、版本、哈希、模型及参数 schema）、归一化参数和 seed 深拷贝进 job JSON。视频还保存每个输入镜头的确定 seed：`(job.seed + index) mod 2^64`。队列执行和重启恢复只能使用 job 中的快照与参数；当前工作流文件的后续替换不会改变已提交任务。

无 `selectionSnapshot`、无 `workflowSnapshot` 或快照与任务参数不一致的旧排队任务在申请模型前失败，分别给出 `SNAPSHOT_INVALID` 或 `WORKFLOW_SNAPSHOT_INVALID`。保留旧任务供调查，不能用当前选优或当前工作流隐式补齐。原图不存在、非 JPEG 或内容哈希变化也会失败，不会改读 develop/AI 变体。

## 队列、恢复和失败

运行时通过 `ModelController.use(image|video)` 共享单工作者模型调度。已有 `promptId` 只查询 ComfyUI history 和 queue；队列内任务继续等待，历史完成则下载，明确失败立即终止，连续三次缺失或服务不可达即失败，不会反复重提交。执行轮询最多 360 次，每次间隔 5 秒。模型资源申请连续失败最多三次，每次间隔 30 秒，随后 `RESOURCE_RETRY_EXHAUSTED`。显式 retry 总 attempt 最多三次，并保留冻结快照、参数、seed 与已完成镜头。

图片已保存的 `ai-{jobId}` 变体在恢复时直接确认完成。视频每个镜头先写 `.pending.mp4`，再原子替换为 `{index}.mp4`，保存 `done`。已完成且文件存在的镜头不会再次生成；已有 prompt 而镜头文件缺失时会对账历史并重下载。所有镜头完成后 ffmpeg 合成为 `memory.pending.mp4`，再原子替换 `memory.mp4`；最终文件存在时重启可直接确认完成。不会自动重试 ComfyUI 明确失败的 prompt；需要调用相应 retry 路由，未完成镜头才会重新排队。

## 验证边界

本节点用合成 JPEG、假 Comfy 响应及假 ffmpeg 测试队列语义，没有启动 GPU 或验证真实模型产物。真实 Spark 队列、历史保留期、模型互斥及图像/视频质量仍由后续 runtime 验收。
