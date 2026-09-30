# Wander Bound｜Python FastAPI 主服务

`pyserver.app` 是唯一应用入口。各模块有独立目录和多个文件：

| 模块 | 职责 |
| --- | --- |
| `agent/` | Step Plan 流式 Agent loop、会话状态、工具编排、供应商发现、计划与降级 |
| `providers/` | MCP HTTP 客户端、高德非 MCP 查询；不解析供应商原始 MCP 业务信封 |
| `trips/` | 行程状态、历史和持久化 |
| `settings/` | `config.yml`、密钥和来源优先级 |
| `media/` | 私有照片存储、选优（EXIF 信号、L0 质量分、连拍去重、VLM 打标）、精修调色、Spark ComfyUI 与 MiniMax H3 作业、鉴权、媒体接口。选优产出交给精修（`selected-photos`）和回忆剪辑（素材卡）两个下游，见 `docs/photo-curation.md` |
| `inference/` | Spark 模型按需启停、共享内存观察、媒体任务互斥与 Web 调试接口 |
| `api/` | 健康、能力、规划流和网页资源 |

供应商 MCP 运行于 DGX Spark Docker。`TRAVEL_DATA_MCP_URL` 用于调用 Node 归一化工具；`TRAVEL_OTA_MCP_URL`、`TRAVEL_12306_MCP_URL`、`TRAVEL_DIDA_MCP_URL` 用于真实 `tools/list` 展示。Python 不运行 Docker，也不调用旧 Node `/api/data/*`。图片工作流经本地到 Spark 的 ComfyUI API 隧道调用。

照片选优分两步。上传时 `images.extract_exif` 把拍摄时间、GPS、设备、朝向、35mm 等效焦距和曝光读进 metadata，`images.normalize` 同时去掉 EXIF、把长边收到 2560。随后 `quality` 加 `curate` 走不依赖模型的 L0：清晰度、曝光、ISO 噪点评分，分块清晰度分布，运动模糊方向性，dHash 连拍去重，排序，结果由 `store.set_quality` 写回。配上多模态端点后，`vlm` 在存活的候选上叠一层语义标签和保留分。判废由这三层分担，不交给任何一方单独拍板，理由见 `docs/photo-curation.md`。

本地运行 `./spark-tunnel.sh` 和 `./start.sh`。测试：`.venv/bin/python -m pytest pyserver/tests -q`。

Spark 部署设置 `SPARK_MODEL_CONTROL=1` 后，`/api/inference/status` 提供模型和资源状态；媒体任务经单一工作队列串行执行。`SPARK_QWEN38_STICKY=1` 让 Qwen 优先常驻：图片可在内存足够时与它并存，视频任务会临时释放它，任务结束后自动恢复。图片与视频空闲 600 秒后停止。Web 的“模型调度”页可观察队列、内存、GPU 利用率、Qwen 权重加载阶段和媒体任务阶段；生成中的百分比不可可靠获取时显示活动进度。手动预热、释放及 Qwen3.8 测试接口要求 `MEDIA_API_TOKEN`。本地开发默认观察模式，不执行 `systemctl`。Qwen3.8 使用独立的 `deploy/spark/qwen38.service`；未安装该单元时 Web 显示“尚未部署”，现有 Step Plan 不变。

Spark 上的手帐图片、旅行短片与手帐素材白天提交后写入持久化队列，默认在 `Asia/Shanghai` 的 23:00–07:00 自动开工。夜间还要连续 30 秒满足空闲条件：无正在运行或加载的模型任务、`MemAvailable` 不低于 16 GiB、内存 PSI some/full 分别不高于 5%/1%、每核一分钟 CPU load 不高于 0.75、GPU 利用率不高于 20%（GB10 未提供此读数时使用其余信号）。忙碌时每 30 秒重新采样；运行中的任务会完成当前件再判断下一件。服务重启后从落盘队列继续。交互式照片重绘仍即时领取。夜间时区与窗口可由 `SPARK_NIGHT_TIMEZONE`、`SPARK_NIGHT_START`、`SPARK_NIGHT_END` 调整。
