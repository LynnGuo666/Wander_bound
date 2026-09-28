# M03 执行基线复核｜2026-09-28

## 核对边界

本轮本地代码为 `feat/m01-local-generation-foundation@37ecdc75a5977974c44f43c76cf5ac1c2093d752`，工作树基于 `24aae844` 并包含 `86e0d48`、`d6a3d88`、`1f553ad`、`b0278a7`、`ccf6dde`、`37ecdc7`。M03 原 `node.m03.baseline` 仍引用 `4c31149`，因此需要单独的 `baseline-37ecdc7` 补充，原历史节点保留。主会话报告已将 `37ecdc75` 部署到 Spark 独立分支；本轮没有连接 Spark、读取私有照片、调用 Step 或启动 GPU，部署状态与实际模型可用性不由本轮独立证明。

VibeHub V3 `task_brief` 显示 M03 为 `active`、full profile，四项必需 criterion 仍为 `accepted`；原 `gate`、`storyboard`、`shots`、`compose`、`review` 均为 `planned`。M01 `task_brief` 显示任务仍为 `active` 且四项必需 criterion 为 `accepted`。M03 gate 原计划要求读取 M01 完成状态和证据；因此本轮基线核对不会把 M01 代码提交、合成测试或主会话的部署报告当作跨任务门禁通过。旧 `session.plan-amend.t3.20260928` 的 typed timeline 仅有绑定、增加 baseline、修改 gate 依赖和解绑，没有 open/close；保留其 unknown 完整性缺口。

## 已有公共接口与影响

- `MediaStore.selection_record(tripId)` 与 `selected_original_snapshot` 固定已提交清单的 `tripId`、`batchId`、`source`、`updatedAt`、完整 `photoIds`、输入顺序及 SHA-256；仅已选、本行程、可读的规范化 JPEG original 能作为输入。原图消失或内容变化会失败，不改用 develop/AI 版本。
- `POST /api/media/generation-jobs` 仅创建 `scrapbook|storyboard|video` 的 `prepared` 任务，`executionReady=false`，其中 storyboard/video 为 1–8 张。状态与结果读取端点已存在；分镜确认、H3 正式调度、成片结果写入与下载尚未接入这些新 DTO。旧 `/api/media/memories` 有 H3 视频执行路径，但并非 M03 所需的 Step 分镜、用户确认和配乐成片流程。
- `ComfyClient.freeze_workflow()` 固定 API 图、版本、哈希、模型节点、参数 schema 与输入画布策略；job 保存完整快照、参数、seed，视频逐镜头确定 seed。运行前持久化规范 UUID `promptId`，adapter 向 `/prompt` 传相同 ID 并核验响应；重启/响应丢失时查 history/queue，不自动重投未知请求。Comfy 服务本身不保证相同 ID 的重复 POST 去重。无旧快照任务明确失败。
- H3 manifest/API 图规定 `1024×576`、严格 `16:9`、默认 124 帧/24 fps（约 5.17 秒），帧数 124–362 且步长 17。当前只有源码、工作流及本地替身测试证据；真实 H3 单镜头探针、实际尺寸/可解码性、耗时与显存尚待主会话验证。四镜头默认时长不能写成精确 20 秒。

## Step 素材卡缺口及首版策略

`ConfigStore.credentials()` 能从私有配置或环境取 `stepfun`；主会话只读检查 `bool=True`，不能据此认定 Step API 调用成功。现有 `pyserver/agent/step.py` 是行程规划用的 `step-5-preview` 流式客户端，尚无媒体分镜专用结构化输出、schema 校验、有限重试及确认版本接口。

`MediaStore` 照片元数据目前有 `tripId`、日期、尺寸、基础 analysis 等，没有可复用的场景描述/主体/地点/时间及来源素材卡 API。`docs/validation-assets/` 的四张公开照片有人工描述与来源许可，可作为未来有来源文字卡的测试输入；它们是不同日期的验收集合，不代表一次真实旅行，也不证明自动素材卡已上线。首版应为每个 selected photoId 建立服务器校验的文字卡映射：`photoId`、描述/主体/地点/时间的可选字段、每字段来源或 `unknown`。缺失字段明确标记未知，允许用户补充且记录来源；不得由文件名或模型猜测为事实。发往 Step 的只能是确认用于该批 selected 快照的文字 JSON，默认不上传 JPEG。未知/越行程/未入选卡必须拒绝。字段格式、存储与 API 归属需在 gate 节点定稿，不能把仓库 fixture 直接当生产媒体元数据。

## 后续节点准入与证据

1. **gate**：保留原跨任务前置。先核实 M01 typed 完成/验收及真实 H3 单镜头探针，再用真实 selected 批次映射有来源文字卡；Step 配置仅证明可配置，需成功调用及出站仅文字证据。缺照片或卡字段按首版策略反馈，不能补未选照片。
2. **storyboard**：定义有界 `shotId/photoId/order/role/duration/prompt/motion/transition` schema，校验来源快照、重复/未知 ID、顺序、时长与 JSON 错误；草稿可编辑，但只把用户明确确认的版本交给昂贵 H3。真实 Step 调用、超时及错误 JSON 必须实测，不能把规划客户端既有能力视为已实现。
3. **shots**：每张 selected original 结合对应确认分镜调用本地 H3；固定 workflow/参数/seed/promptId，按 history/queue 恢复。完成镜头须检查文件存在、可解码且画幅正确后才复用。真实动态、显存/耗时与失败恢复仍需证据。
4. **compose/review**：先取得来源与授权可核查的本地配乐或用户提供音乐；无合法音乐时可做无声调试，不能宣称含音乐 criterion 通过。FFmpeg 应验证最终严格 16:9、正确顺序、转场重叠后的实际时长、音量与淡入淡出，并以 ffprobe、播放检查、下载、重启后同一产物及至少一支完整真实 H3 短片复核四项 criterion。不得用静态缩放或示例片替代。

本轮只做基线核对与计划补充，不变更产品决定、实现业务或 review 任何 criterion。
