# 私有相册与 DGX Spark 媒体工作流

iOS 通过 PhotoKit 或系统照片选择器读取用户选中的照片。上传确认页说明原始 EXIF（可能包括精确位置）会私存服务器；对外图像去除 EXIF。Python FastAPI 的 `pyserver/media/` 保存照片与行程关联，重新编码 JPEG、去除 EXIF；自然与电影感预设使用 Pillow 做本地图像处理。创意重绘通过私网 ComfyUI 调用 DGX Spark 上的 Qwen-Image 2.1；回忆短片使用 Spark 上的本地 MiniMax H3 I2V 工作流逐镜头生成，再由本地 ffmpeg 拼接。这里的 MiniMax 是节点本地模型，不是云 API。

| Python 模块 | 职责 |
| --- | --- |
| `photo_routes.py` | 上传、列表、读取和基础增强 |
| `job_routes.py` | 重绘与短片任务、状态、重试、视频下载 |
| `store.py` | 私有文件与照片元数据 |
| `images.py` | 去元数据、尺寸归一化和本地图像预设 |
| `comfy.py` | Spark ComfyUI HTTP 工作流客户端 |
| `jobs.py` | 持久化任务状态、重启恢复、按镜头生成及 ffmpeg 合成 |
| `auth.py` | 媒体 API 的独立 Bearer 令牌校验 |

媒体 API 包括 `POST /api/media/photos`、`GET /api/media/photos?tripId=...`、`GET /api/media/photos/{id}`、`POST /api/media/photos/{id}/enhance`、`POST /api/media/photos/{id}/redraw`、`GET /api/media/edits/{id}`、`POST /api/media/memories`、`GET /api/media/memories/{id}` 以及 `GET /api/media/memories/{id}/video`。所有私有 API 使用账号会话 `Authorization: Bearer <session>`。邀请码注册首位管理员，管理员再生成一次性邀请码；账号之间按 ownerId 隔离。无会话返回 401。

本地调试先启动 `./spark-comfy-tunnel.sh`，再运行 `./start.sh`。默认图像 API 为 `http://127.0.0.1:18191`，视频 API 为 `http://127.0.0.1:18188`；照片重绘与视频工作流分别是 `workflows/qwen-image-2.1-edit-api.json` 和 `workflows/minimax-h3-i2v-api.json`。城市封面可使用 `workflows/qwen-image-2.1-t2i-api.json` 进行无参考图文生图：它从 `EmptyLatentImage` 开始，不上传图片，也不在提示词前加 `<image1>`。Spark 已部署的同一套 Qwen 模型权重和 ComfyUI 服务即可执行该图；当前应用的媒体 API 仍绑定照片重绘工作流，文生图需单独提交这份工作流。Spark 上的 ComfyUI 保持私有，不向公网开放。只运行旅行规划时无需启动媒体隧道。

本地 Vite 的开发者调试页使用 `?debug=1`，其 `/api/inference` 请求通过 Tailscale 私网转发到 Spark，以展示真实的内存、GPU 与模型状态；其他 `/api` 请求仍由本地 FastAPI 处理。需要换私网入口时可在启动 Vite 前设置 `SPARK_DEBUG_API_URL`。Spark 部署页面直接访问同源的模型状态接口。

已验证的城市封面提示词存于 `prompts/city-cover.qwen-image-2.1.json`，内有用途标签、可替换变量、seed 和深圳湾实例。连接媒体隧道后可直接运行：

```bash
python3 scripts/generate-city-cover.py --city 深圳湾 --landmarks '平安金融中心与深圳现代天际线' --foreground '海滨步道、栏杆和几株亚热带树木' --output ../output/shenzhen-cover.png
```

图像与视频推理取决于 Spark 上模型和工作流的实际运行状态。应用目前是本地单进程作业队列，多用户身份隔离、跨进程资源锁、存储配额和自动识别旅游照片仍未实现；正式多人使用前需要补齐。

迁移前的 Node 媒体实现和详细实验记录保存在 Git 标签 `archive/node-server`。研究笔记 `MEDIA_MODEL_RESEARCH.md` 描述的是当时的实现，不是现行代码路径。
