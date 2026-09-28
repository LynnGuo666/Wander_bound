# M01 本地生成公共基础交接（v1，2026-09-28）

本交接对应 `task.m01.931bf5bbc699 / node.m01.handoff`。适用源码基线 `feat/m01-local-generation-foundation@7528734d4411b219aece99fe39074f82de3c5593`；正式只读 API 检查的 Spark 验证分支为 `f4aea97abb70bc044708cba32990218b10217257`。本地 7528734 后于远端 f4aea97 的内存字段解释修正：`memory.availableGiB` 是 `/proc/meminfo` 的 `MemAvailable`，真实采样最低系统可用内存 44.9 GiB，**不是显存或峰值**。本交接没有部署、提交 GPU 作业或改变远端媒体。完整字段依据 [公共素材契约](local-generation-contract.md)、[版本化工作流](local-workflows.md)、[运行与恢复](local-runtime.md)；下文列出 M02/M03 可以直接依赖的接口及必须自行实现的业务部分。

## 1. 已存在的请求与资格合同

媒体请求需要 `Authorization: Bearer <media token>`。正式 selected 清单使用 `GET/PUT /api/media/trips/{tripId}/selected-photos`；PUT 保存 `batchId`、`source`、`photoIds`、服务器 `updatedAt`。本次公开验收 trip `c2712842-c987-4347-938b-b6bc6fa7905e` 的 batch 为 `m01-public-yellowstone-20260928-v1`、`source=manual-acceptance-20260928`。这是不同日期四图的人工集合，不能称为真实同次旅行、自动选优或生产素材卡。

`POST /api/media/generation-jobs` 仅收以下严格 JSON（多余字段 400）：

```json
{"productKind":"scrapbook","tripId":"<真实 TripStore UUID>","photoIds":["<本 trip 的已选 photoId>"],"prompt":"<可选，1–4000 字符>"}
```

`productKind` 为 `scrapbook|storyboard|video`；scrapbook 恰 1 图，storyboard/video 为 1–8 图。所有 photoId 必须不重复、属于该 trip 且位于**当前已正式提交**的 selected 清单。读取 `MediaStore.bytes(photoId, "original")`，要求非空、Pillow 可完整解码的规范化 JPEG；不会用 develop/AI 变体或全量上传列表替代。服务端存 `selectionSnapshot` 深拷贝：`schemaVersion=1`, `tripId`, `selection.{tripId,batchId,source,updatedAt,photoIds,sha256}`, `inputPhotoIds`（实际请求顺序）, `originals[{photoId,sha256}]`, `inputVariant="original"`。清单 hash 用规范 JSON，original hash 绑定内容；后续清单变化不换已排队输入，执行前重验原图，不可读/变化明确失败。客户端送 `selectionSnapshot`/`inputVariant` 会按未知字段拒绝，不得信客户端伪造资格。实现见 `pyserver/media/contracts.py:31-164`。

创建返回 HTTP 201：`{id,productKind,resultKind,status:"prepared",executionReady:false,selectionSnapshot}`，其中 `resultKind=image|storyboard_json|video`。`GET /api/media/generation-jobs/{id}` 返回 `id,productKind,resultKind,status,executionReady,backend,createdAt,startedAt,completedAt,selectionSnapshot,result,error`；`GET .../{id}/result` 在尚未成功时为 HTTP 409，JSON `detail.code=RESULT_NOT_READY`。当前 product job 保留私有 prompt、`backend=null,result=null,error=null`，**不调度 worker，也没有产品 retry/下载 URL 或产物 schema**。M02/M03 不得把 `prepared`、旧 edit/memory 成品或 `executionReady=false` 当成手帐/分镜/视频业务已完成。实现见 `jobs.py:101-120`、`job_routes.py:73-105`。

FastAPI 结构化合同错误的实际 JSON 外层为 `{"detail":{"code":"...","message":"..."}}`，不是顶层 `{code,message}`。本地完整 HTTP 集成测试覆盖 201、409 `RESULT_NOT_READY`、400/404/409 资格反例（`pyserver/tests/test_generation_contract.py:73-141`）；核心码包括 `SELECTION_MISSING/EMPTY/INVALID`, `PHOTO_IDS_INVALID/DUPLICATE`, `PHOTO_NOT_FOUND/WRONG_TRIP/NOT_SELECTED`, `ORIGINAL_UNREADABLE/CHANGED`, `SNAPSHOT_INVALID`, `REQUEST_INVALID`, `PROMPT_INVALID`。部分旧路由的 404 仍是字符串 `detail`；客户端应按具体路由解析。未在此次 Spark 只读检查里重新触发错误 POST，不把本地测试称为远端实测错误码。

## 2. 已可执行的旧探针与可复用运行基础

`POST /api/media/photos/{photoId}/redraw`（单图，`prompt`, 可选 `seed/parameters`）和 `POST /api/media/memories`（`tripId,photoIds,title`, 可选 `seed/parameters`）仍返回 202 并进入同一个 controller/单 worker；两者也要求 selected original。查询 `GET /api/media/edits/{id}` / `GET /api/media/memories/{id}`，图片从 `GET /api/media/photos/{photoId}?variant=ai-{jobId}` 读取，视频从 `GET /api/media/memories/{id}/video` 下载。仅 failed 的旧 job 可 `POST /api/media/edits/{id}/retry` 或 `/memories/{id}/retry`；错误 kind 路由不改 job，attempt 最多 3，结果未知返回 409 `detail.code=PROMPT_OUTCOME_UNKNOWN` 且不分配新 UUID。这些旧路由仍可用，却没有 M02 五风格整页或 M03 Step 分镜/配乐成片语义。

旧可执行 job 在提交时冻结 `selectionSnapshot`、`workflowSnapshot`、受 schema 约束的 `parameters` 和明确落盘的 `seed`；video 按输入顺序保存逐镜头 seed。`workflowSnapshot` 是 JSON 深拷贝，含 schema version、workflow id/version/hash、snapshot hash、API graph、engine/model/custom-node metadata、parameter schema 和 input policy。`ComfyClient.queue(image,prompt,seed,workflow_snapshot=...,parameters=...,prompt_id=...)` 用保存图，不读后续默认图。prompt UUID 在发送前持久化；API 重启或响应丢失先查相同 UUID 的 Comfy history/queue，已完成镜头不重复采样；missing 有界失败，结果未知的人工 retry 被 409 挡住，明确拒绝/失败才在最多三次总 attempt 内用新 UUID。详情 `jobs.py:62-99,122-472`、`comfy.py:49-115`、`workflow_versions.py:27-101`、[真实恢复证据](generated-evidence/m01/runtime-loss-accepted.json)。普通日志不应输出原照片、prompt 或 token。

Qwen 图 `travel.qwen-image-2.1.edit` 真实输出 `1248×832` 3:2；H3 `travel.minimax-h3.i2v` 1.0.0 旧快照固定 `contain-white-v1`，1.1.0 采用 `contain-or-cover-v2`，`fit_mode=cover|contain`、默认 cover，上传画布严格 `1024×576`，真实 H3 单镜头 cover 已消除旧侧边白边。center crop 对本次 1920×1227 纵向去掉 147 像素约 11.98%，需下游按素材选择构图；旧快照不变。UI/APP mode 本身不执行服务端 cover 预处理。Qwen 水彩/黏土/剪纸与 H3 cover 均为**公共探针**，不代表 M02 五风格预设或 M03 约 20 秒成片验收。H3 此次在线 history 未取得，片内 metadata 仅辅助确认 124 帧/seed；真实正式 job 与可解码产物另有 API/FFprobe 证据。新 H3 含非静音 AAC，但其内容/来源/许可未知，不能当合法配乐。

## 3. M02 与 M03 直接派工差距

| 负责人 | 输入与输出决定 | 当前缺口及共享文件协调 |
| --- | --- | --- |
| M02 手帐 | 一张 selected original 对一张 3:2 整页；五个版本化 `styleId`（水彩、剪纸、黏土、网点漫画、像素），可选短标题；输出整场景、相关贴纸、纸底、缩略图/下载、真实状态错误。 | 产品 DTO 目前拒绝 `styleId/title/seed/parameters`；无 runner/结果 schema/下载。优先独立 `scrapbook` 模块实现风格和排版，**需要主会话协调** `contracts.py`, `job_routes.py`, `jobs.py` 的严格 DTO、worker 和结果接线，可能用 `images.py`。五风格同图真实效果及无/中/英文标题须另验。V3 `node.m02.gate/presets/render`。 |
| M03 分镜/视频 | 1–8 张 selected original；文字卡 → Step `step-5-preview` 草稿 → 用户编辑并确认不可变分镜版本 → 各镜头 H3 → 约 20 秒含合法音乐 16:9 MP4、封面、下载与恢复。 | 无生产素材卡持久化/API、Step 分镜调用成功证据、确认接口、产品 video runner/结果/下载。优先独立卡/分镜/成片模块；需主会话协调相同共用 DTO/route/job 文件，`store.py` 或卡库、`pyserver/agent/step.py`、FFmpeg 输出。照片默认不上传 Step，只送可信文字 JSON。V3 `node.m03.gate/storyboard/shots/compose/review`。 |

M03 卡建议每项以 `photoId` 绑定 `sceneDescription`, `subject`, `place`, `capturedAt` 及逐字段 `source`/known 状态；来源未知就标 unknown 或请用户补充，不能从文件名捏造人物地点。校验卡属于冻结 selected 快照，防越 trip/未选/重复。现有 `MediaStore` 只有 `capturedDay`、尺寸、原图与 variants，没有生产场景卡；`pyserver/agent/step.py` 是行程规划流式客户端。Step credential 存在的只读报告不等于 Step 分镜调用成功。

人工四图文字 source 映射来自 [许可与完整出处](validation-assets/README.md)：秋山/金树 `199b155d-0c14-4673-8d25-5de27f175676`（Diane Renkin/NPS，2014-10-10）；河岸麋鹿 `5869d8f2-b80b-466a-a724-7f9702e0a3f0`（NPS Digital Image Archives，个人摄影者/日期未知）；大棱镜航拍 `df012e97-1209-4270-9b6e-1e1f0d8267ee`（Jim Peaco/NPS，2001-07）；Lower Falls 雪季纵幅 `a531f3cb-c2bb-439b-b1bb-04b97fa63dc0`（Jim Peaco/NPS，2014-04-03）。文档人工描述不能冒充上线卡；M03 gate 要固定缺字段策略和 Step 实际通路。

## 4. 本次交接核验与局限

| 要求 | 本次真实结果 | 证据 |
| --- | --- | --- |
| 本地回归 | `.venv/bin/python -m pytest pyserver/tests -q`: 71 passed，7 条 Pillow deprecation warning；`npm run check`: Node tests 与 Vite build 退出 0。首次 npm 沙箱 `listen EPERM 127.0.0.1`，允许本机回环后复跑成功。 | 命令执行收据；首次失败为环境限制，未修改源码。 |
| 正式输入/结果只读 | Spark `f4aea97`，四张 original GET 200/hash 与首次收据一致；正式 selected batch 未变。Qwen 旧 edit `succeeded`/变体 GET 200、SHA `4d19b559…`；H3 旧 memory `succeeded`/视频 GET 200、SHA `9631d518…`；H3 cover job `succeeded`。 | [本次 API 收据](generated-evidence/m01/handoff-api-readonly.json)、[首次素材收据](validation-assets/m01-public-yellowstone-first-run.json)、[H3 cover](generated-evidence/m01/framing-real-probe.json)。未重跑推理或改清单/job。 |
| 124/125 帧 | H3 cover 引擎 clip SHA `93cad7ed…`，24 fps/124 帧；Spark FFmpeg 6.1.1 在自动清理的 `/tmp` 用同一镜头比较：现行重编码 125、去音频仍 125；`-fps_mode:v passthrough` 重编码 124，stream copy 124。额外帧由默认视频时间同步/时间戳处理引起，**非 AAC 音轨本身所必需**；此有界单镜头 CPU 复现未改正式 job。 | [CPU 对比](generated-evidence/m01/handoff-ffmpeg-compare.json)、[真实 H3 收据](generated-evidence/m01/framing-real-probe.json)。M03 正式剪辑/转场/合法配乐需明确目标帧数、PTS/音轨策略及播放/解码验收。 |

本地 Mac 没有 `ffmpeg/ffprobe`，故 CPU 对比在 Spark `/tmp` 上用已装 FFmpeg 执行并自动删除临时目录；未动媒体源文件、Comfy、GPU、服务或部署。上游选优分支是否合并不由本节点决定。旧 `session.plan-amend.t1.20260928` only-bound unknown 仍在，新的 handoff Session 不消除它；VibeHub 控制面修复由独立维护任务处理。M01 c04 与最终 `node.m01.final-review` 留主会话亲审；M02/M03 gate 必须按各自 typed 准入另行判定。
