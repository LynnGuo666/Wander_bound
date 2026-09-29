# 动态照片执行基线（2026-09-29）

本记录对应独立 VibeHub 任务 `task.ai-h3.d664bdd1c091` 的 baseline 节点。它是执行接口调查，不是模型实证。代码基于隔离分支 `feat/dynamic-photo-ai-h3@8144c0f5286bab7a78c6a9a97a2b54199f8fc2b3`。原共享工作树仍为 `main@47c290e972bde3cce4dec0055754259111621cb1`，落后远端四个提交；其 `.gitignore` 修改和未跟踪的 `docs/STATUS_AUDIT_2026-09-28.md` 均未改动。2026-09-29 执行 `git fetch origin main --no-tags` 后，`origin/main` 仍为 `8144c0f`。四个新增提交触及 `pyserver/media/analysis_jobs.py` 与 `vlm.py`，因此后续实现必须以当前隔离分支为准。

## 现有业务边界

- `MediaStore.set_selected` 按行程写入 `batchId/source/photoIds/updatedAt`，整份替换、重复请求无变化；`GET/PUT /api/media/trips/{tripId}/selected-photos` 是真实提交边界。`curate_trip` 只返回推荐，不能代表用户已提交。见 `pyserver/media/store.py`、`curate.py`、`photo_routes.py`。
- `POST /api/media/photos/{photoId}/develop/save` 只保存一张精修图。元数据 `developments[]` 含 `variant/settings/note/width/height/createdAt`；文件名是 `photos/{photoId}-{variant}.jpg`。当前没有整批精修任务、待处理标志或结算事件。逐张保存无法判断哪张是最后一张，精选提交也不能代表精修完成。后续需要提供可运行的后端批次结算入口，由实际精修流程在该批处理结束时调用；结算写入后自动排入动态照片任务，不要求人工选图。
- `selected_original_snapshot` 已冻结提交清单的哈希、所请求照片 ID 和原图哈希，但 `inputVariant` 固定 `original`；旧 scrapbook/memory 产品依赖这个限制。新动态照片应建立独立快照，记录每张已选照片的原图或最新有效精修 variant、内容哈希、实际尺寸、精修版本与清单哈希。声明过的精修版本文件丢失或损坏时必须报错，不能回退原图。冻结后重读要验证哈希及清单身份。
- `AnalysisJobs` 提供可恢复的批次 L0/VLM 分析，结果 `recommended` 并非最终精选。视觉标签来自原图，`tag_image` 发送压缩后的真实像素至共享视觉服务。已有标签没有输入 variant/hash 绑定，精修后不能无条件复用。旧分析失败会保留 L0 推荐；动态选图需要独立失败语义，不能把服务错误当成 `skipped`。`develop.suggest/review` 也直接发送真实像素到视觉服务。Step 现有手帐接口只发送文字标签，不发送图片；可用于文字整理，但不能把它的标签当作动态画面证据。
- `JobStore` 有本地单 worker、`ModelController.use` 的共享模型串行控制、工作流快照/seed、持久 prompt UUID、Comfy history/queue 对账、结果文件恢复及最多三次显式任务尝试。新动态产品可复用这些机制，同时避免改动旧 memory 的 selected-original 和多镜头语义。账户由应用中间件鉴权；`MediaStore.get`、`JobStore.get` 与 `TripStore.get` 按 `ownerId` 过滤，新状态和视频路由须同样检查行程与账号。
- 当前 H3 manifest 为 `travel.minimax-h3.i2v@1.1.0`：1024×576，124 帧，24 fps，`17k+5` 帧网格，旧输入策略为 `contain-or-cover-v2` 且默认 `cover`。`ComfyClient.queue` 强制 1024×576；`JobStore._video_file_valid` 强制 16:9；旧 memory 每镜头使用固定提示词，末尾 FFmpeg concat 为 AAC 音轨路径。新产品应有独立可变比例尺寸映射与约 5 秒帧数（124/24≈5.17 秒），先在真实 H3 环境核实 stride/尺寸约束，再做非 16:9 实模验收；无音轨、全帧解码和动态观感均需独立检查。

## 拟定新链路契约

1. `PUT selected-photos` 只创建/更新提交批次。定义可调用的 `POST /api/media/trips/{tripId}/dynamic-photo/settle` 后端工作流入口，携带当前 `batchId` 和每张精修结论；它对照当前完整清单与批次版本，写入结算并自动排入处理。逐张 `develop/save` 后由实际流程调用此入口；若要无客户端改动，需由后端精修编排器在全部逐张操作结束时调用。结算前保持等待，不根据 `developments[]` 缺失猜测“已结算”。旧批次或清单变更应拒绝结算，不能对新清单误启动旧任务。
2. 对每张候选冻结 `photoId/sourceVariant/variantCreatedAt/sha256/width/height`。`ownerId + tripId + batchId + 完整清单 hash + 精修结算版本 + 各输入 hash + 选择器版本 + H3 工作流版本` 组成去重身份。持久任务索引以原子写入/进程锁或等价 CAS 保证同身份并发只创建一个任务；显式重试在同一任务上按 `attempt` CAS 更新，不允许排队期间输入改变后复用旧身份。重读快照失败时保留原目标并报错，不自动切换新图。
3. 对冻结的实际像素调用本地视觉通路，返回逐张适合度、理由、排序、至多一张目标和轻微运动描述；严格校验 ID/格式/数量。全不适合为 `skipped`，模型故障为 `failed`。新结果保存选择器 prompt/model 版本。
4. 选中目标进入单图 H3 队列，用共享 controller 和已冻结 prompt UUID；保留所选 photoId。比例方案先以源宽高比挑选模型允许的画布尺寸，按已安装节点源码的宽高步长 32 对齐并记录相对比例误差；必要的微小补边要记录，不能中心裁切或拉伸。当前仓库旧图设置为 1024×576/124 帧；非 16:9 尺寸在 Spark 上的实际可运行性仍必须通过真实推理验证。成功文件先检验容器、全部帧、无音轨、宽高比例和时长，再持久化动态关联。失败保留静态图，显式有限重试同一目标。
5. 新路由返回批次状态、选择理由和 `photoId` 的动态版本；MP4 与封面只经账户及行程鉴权读取。后续页面可以按稳定 photoId 回退静态图，本任务不改 Web/iOS 页面。

## 验证边界与未决项

- 2026-09-29 12:32 CST，使用既有可信 host key 与本轮授权的交互式 SSH 登录后只读核对 Spark：`/home/Developer/travel-agent` 位于 `deploy/8144c0f`，HEAD 为 `8144c0f5286bab7a78c6a9a97a2b54199f8fc2b3`，工作树 clean，与本地隔离分支一致。`travel-agent.service` active（12:03 CST 启动）；`minimax-h3-comfy.service`、`qwen21-comfy.service` inactive；`qwen38.service` active，回环 `/v1/models` 返回 `qwen38-27b`。应用 `/api/health` 返回 ok。直接读取持久任务目录 `data/media/jobs` 的 24 个 JSON：本次快照里 queued/running/loading_model 共 0，另有成功/失败历史任务；选优清单 1 份，分析任务 0 份。H3 Comfy 回环 `/system_stats` 因服务未启动而不可连接。这些仅是瞬时状态，没有启动 GPU 任务或修改共享服务。
- H3 用户服务的工作目录是 `/home/Developer/minimax-h3-dgx-spark/ComfyUI`，源码提交 `e80c1570b6b44a2557d5d8e341e05782d18c9bbb`；受控节点 `MiniMaxH3ImageToVideo` 的宽高输入步长为 32，源码常量 `CANVAS_MULTIPLE=32`、`MAX_PIXELS=768×1344`、`FPS=24`，帧数按 `17k+5` 对齐，124 帧为约 5.17 秒。节点把 `first_frame` 直接缩放到请求画布，故新链路必须按源图比例选尺寸并记录微小对齐误差，不能把不匹配的画布交给节点。H3 服务本次 inactive，因此这些是已安装源码和服务配置核对；非 16:9 的实际可运行性、主体稳定与完整解码仍待真实生成验证。Comfy 仓库有未跟踪的 `workflows/` 目录，本轮未改动或清理。
- baseline 本地代码契约来自上述文件，尚未通过当前分支的自动化回归；后续 sources/selection/h3/integration 节点会各自运行针对性测试，最终 review 节点跑全量回归。真实 AI/H3、非 16:9 片段、精修输入与鉴权播放必须在 real-validation 节点提供新证据，不能引用旧 16:9 探针充数。
