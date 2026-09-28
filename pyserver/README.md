# Python FastAPI 主服务

`pyserver.app` 是唯一应用入口。各模块有独立目录和多个文件：

| 模块 | 职责 |
| --- | --- |
| `agent/` | Step Plan 流式 Agent loop、会话状态、工具编排、供应商发现、计划与降级 |
| `providers/` | MCP HTTP 客户端、高德非 MCP 查询；不解析供应商原始 MCP 业务信封 |
| `trips/` | 行程状态、历史和持久化 |
| `settings/` | `config.yml`、密钥和来源优先级 |
| `media/` | 私有照片存储、选优（EXIF 信号、L0 质量分、连拍去重、VLM 打标）、精修调色、Spark ComfyUI 与 MiniMax H3 作业、鉴权、媒体接口。选优产出交给精修（`selected-photos`）和回忆剪辑（素材卡）两个下游，见 `docs/photo-curation.md` |
| `api/` | 健康、能力、规划流和网页资源 |

供应商 MCP 运行于 DGX Spark Docker。`TRAVEL_DATA_MCP_URL` 用于调用 Node 归一化工具；`TRAVEL_OTA_MCP_URL`、`TRAVEL_12306_MCP_URL`、`TRAVEL_DIDA_MCP_URL` 用于真实 `tools/list` 展示。Python 不运行 Docker，也不调用旧 Node `/api/data/*`。图片工作流经本地到 Spark 的 ComfyUI API 隧道调用。

照片选优分两步。上传时 `images.extract_exif` 把拍摄时间、GPS、设备、朝向、35mm 等效焦距和曝光读进 metadata，`images.normalize` 同时去掉 EXIF、把长边收到 2560。随后 `quality` 加 `curate` 走不依赖模型的 L0：清晰度、曝光、ISO 噪点评分，分块清晰度分布，运动模糊方向性，dHash 连拍去重，排序，结果由 `store.set_quality` 写回。配上多模态端点后，`vlm` 在存活的候选上叠一层语义标签和保留分。判废由这三层分担，不交给任何一方单独拍板，理由见 `docs/photo-curation.md`。

本地运行 `./spark-tunnel.sh` 和 `./start.sh`。测试：`.venv/bin/python -m pytest pyserver/tests -q`。
