# 私有相册与 DGX Spark 媒体架构

## 数据边界

```mermaid
flowchart LR
  A[iOS PhotoKit 本机日期筛选] --> B[用户选择照片]
  B --> C[iOS 导出 JPEG]
  C --> D[私有媒体 API]
  D --> E[去 EXIF、分析、修图与私有存储]
  E --> F[DGX Spark 上的 ComfyUI / MiniMax H3]
  F --> G[本地 FFmpeg 合成并保存 MP4]
  H[行程需求] --> I[服务端解析与记忆过滤]
  I --> J[外部 Step 5 仅接收结构化需求]
  I --> K[外部票务、酒店和地图服务仅接收查询必需字段]
```

- PhotoKit 在 iPhone 上按用户选择的日期扫描照片；系统可能只授予“有限相册访问”。扫描结果不会自动上传。用户选中的照片先在设备上重新导出 JPEG，服务端再次重新编码，移除 EXIF、GPS 与设备信息。服务端只记录行程标识和拍摄日期，不保存精确位置。
- 图片质量分析（亮度、清晰度与信息量）和自然/电影感调色由私有媒体服务执行。它们是可复现的本地图像处理，不能伪称已使用生成式修图模型。原图和修图版本分开存放。
- 回忆短片经用户主动点击后才提交。每张照片成为本地 MiniMax H3 I2V 镜头；多个 MP4 由本地 FFmpeg 合成。媒体接口不调用 MiniMax 云 API，也不向外部 Step 模型发送相册图片。
- 私有相册用旅程名称与日期范围标识，可管理当前或历史旅程。短片状态查询会启动后台合成并立即返回运行中；客户端继续轮询，不等待 HTTP 请求内完成整个视频编码。
- 外部 Step 模型只接收城市、日期和必要偏好的结构化字段；原始自由文本、酒店品牌、预算、逐条到访记录和相册内容不发送。外部供应商仍会收到完成查询所必需的城市、日期、地点等字段。
- 媒体接口需要单独的 `MEDIA_API_TOKEN`，iOS 将令牌放入 Keychain。生产环境通过 HTTPS/Tailscale 私网访问，不在公网无鉴权开放 ComfyUI 或照片目录。

## 服务端模块

| 模块 | 职责 |
| --- | --- |
| `server/media/routes.mjs` | 独立鉴权、上传大小限制、照片与任务 API |
| `server/media/store.mjs` | 私有原图、修图版、任务记录和视频文件 |
| `server/media/images.mjs` | 重新编码去元数据、图像统计和本地调色 |
| `server/media/comfy.mjs` | 仅连接本机或私网的 ComfyUI，上传图片、填充 H3 工作流、查询结果 |
| `server/media/memories.mjs` | 持久化多镜头任务并在本地 FFmpeg 合成 |

媒体 API：`POST /api/media/photos` 上传 JPEG（请求头 `X-Trip-Id`、可选 `X-Captured-Day`）；`GET /api/media/photos?tripId=...` 列表；`GET /api/media/photos/:id?variant=original|natural|cinematic` 取图；`POST /api/media/photos/:id/enhance` 修图；`POST /api/media/memories` 创建短片；`GET /api/media/memories/:id` 查任务；`GET /api/media/memories/:id/video` 下载本地 MP4。所有接口要求 `Authorization: Bearer <MEDIA_API_TOKEN>`，且默认未配置令牌时不可用。图像处理模块只在媒体接口请求时导入。

## DGX Spark 上的 MiniMax H3

Spark 节点已安装 ComfyUI `0.34.0`、MiniMax H3 FL2VA INT8 模型、NVFP4 文本编码器及视频/音频 VAE。项目的 [I2V API 工作流](workflows/minimax-h3-i2v-api.json)参考 [MiniMax 官方本地部署指南](https://platform.minimax.io/docs/guides/local-deploy-h3)中的 ComfyUI 模板构建：864×480、124 帧、20 步。在本节点用合成风景图实际生成了约 5.17 秒的 H.264/AAC MP4；随后通过旅游 Agent 媒体 API 完成上传、排队、生成、合成、下载，得到约 5.22 秒的 MP4；双镜头本地合成验证得到约 10.42 秒的 MP4。单镜头生成约 7 分钟；更多并发、画质和分辨率仍需实测。之前两次 `audio_scale` 错误来自通用 AuraFlow 采样器的错误连接；此工作流使用 H3 原生条件节点与采样链。

配置步骤：

1. 在 Spark 上启动 ComfyUI，加载官方 MiniMax H3 I2V 对应的本地权重。不要使用调用 MiniMax 云端的 Partner/API 节点。
2. 将 `.env` 的 `SPARK_COMFY_URL` 设为 `http://127.0.0.1:8188`，`SPARK_H3_WORKFLOW_FILE` 设为 `/home/Developer/travel-agent/workflows/minimax-h3-i2v-api.json`；配置独立的 `MEDIA_API_TOKEN`。工作流中的 `__TRAVEL_IMAGE__` 和 `__TRAVEL_PROMPT__` 在创建任务时才填充。
3. 确保本地有 `ffmpeg`；复制 [`deploy/spark/minimax-h3-comfy.service`](deploy/spark/minimax-h3-comfy.service) 和 [`deploy/spark/travel-agent.service`](deploy/spark/travel-agent.service) 到 `~/.config/systemd/user/`，运行 `systemctl --user daemon-reload`，再分别 `systemctl --user enable --now minimax-h3-comfy.service travel-agent.service`。ComfyUI 与旅行 API 分别只监听回环 `8188` 和 `4174`。本节点已启用这两个用户服务。
4. 加入本队 Tailscale 后，iOS“来源”页填写 `http://spark-82.tailb7a50b.ts.net:7000`，在“相册”页输入 Spark 上 `.env` 的媒体令牌，选择照片上传并生成短片。Tailscale Serve 将私网端口 7000 转到回环 API；已有的 Laya 私网端口 9000 保持独立。

本队的 Tailscale 管理配置尚未启用 HTTPS Serve；当前 7000 使用 Tailscale WireGuard 私网内的 HTTP，iOS 仅对此节点域名设置了 ATS 例外，不应把该入口转发到公网。未加入同一 tailnet 的设备无法访问。Spark 上已有的 BTC/Laya 服务与相册服务隔离，不复用其模型或数据。

## 运行前待补

- 媒体 API 的共享令牌适合单人演示；多人使用需独立身份、存储隔离、配额、删除和保留期策略。
- H3 单张短片在 Spark 上约需数分钟；多镜头按顺序排队，正式展示前应预先生成。任务记录持久化，照片与视频目前存储在本机文件系统；正式运行需备份和磁盘配额。
- 日期筛选并不等于语义识别“旅游照片”。后续可在设备端用 Apple Vision 或在 Spark 上部署独立视觉模型做场景分类；当前由用户核对和选择照片。
- 已验证服务端链路使用的是合成测试图片；真实 iPhone 的相册权限、上传体验及生成画质仍需在设备上联调。视频模型可能生成非预期文字或画面，发布或分享前应由用户预览。
