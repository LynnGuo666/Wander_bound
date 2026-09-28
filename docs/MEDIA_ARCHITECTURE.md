# 私有相册与 DGX Spark 媒体工作流

iOS 通过 PhotoKit 读取用户授权的相册，用户选中的照片才会上传。Python FastAPI 的 `pyserver/media/` 保存照片与行程关联，重新编码 JPEG、去除 EXIF；自然与电影感预设使用 Pillow 做本地图像处理。创意重绘通过私网 ComfyUI 调用 DGX Spark 上的 Qwen-Image 2.1；回忆短片使用 Spark 上的本地 MiniMax H3 I2V 工作流逐镜头生成，再由本地 ffmpeg 拼接。这里的 MiniMax 是节点本地模型，不是云 API。

| Python 模块 | 职责 |
| --- | --- |
| `photo_routes.py` | 上传、列表、读取和基础增强 |
| `job_routes.py` | 重绘与短片任务、状态、重试、视频下载 |
| `store.py` | 私有文件与照片元数据 |
| `images.py` | 去元数据、尺寸归一化和本地图像预设 |
| `comfy.py` | Spark ComfyUI HTTP 工作流客户端 |
| `jobs.py` | 持久化任务状态、重启恢复、按镜头生成及 ffmpeg 合成 |
| `auth.py` | 媒体 API 的独立 Bearer 令牌校验 |

媒体 API 包括 `POST /api/media/photos`、`GET /api/media/photos?tripId=...`、`GET /api/media/photos/{id}`、`POST /api/media/photos/{id}/enhance`、`POST /api/media/photos/{id}/redraw`、`GET /api/media/edits/{id}`、`POST /api/media/memories`、`GET /api/media/memories/{id}` 以及 `GET /api/media/memories/{id}/video`。所有媒体请求须使用 `Authorization: Bearer <MEDIA_API_TOKEN>`；缺少令牌时接口不可用。

本地调试先启动 `./spark-comfy-tunnel.sh`，再运行 `./start.sh`。默认图像 API 为 `http://127.0.0.1:18191`，视频 API 为 `http://127.0.0.1:18188`；工作流文件分别是 `workflows/qwen-image-2.1-edit-api.json` 和 `workflows/minimax-h3-i2v-api.json`。Spark 上的 ComfyUI 保持私有，不向公网开放。只运行旅行规划时无需启动媒体隧道。

图像与视频推理取决于 Spark 上模型和工作流的实际运行状态。应用目前是本地单进程作业队列，多用户身份隔离、跨进程资源锁、存储配额和自动识别旅游照片仍未实现；正式多人使用前需要补齐。

迁移前的 Node 媒体实现和详细实验记录保存在 Git 标签 `archive/node-server`。研究笔记 `MEDIA_MODEL_RESEARCH.md` 描述的是当时的实现，不是现行代码路径。
