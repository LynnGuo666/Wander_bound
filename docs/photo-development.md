# 优选照片的调色与裁剪 API

本模块只处理上游已经优选的照片。优选算法、上传入口、Web/iOS 展示、打标、卡片与视频由其他模块负责。上传照片不会自动进入精修队列；优选模块必须明确提交照片 ID 清单。

## 上游交接

照片先通过现有 `POST /api/media/photos` 上传，并关联已有行程。上游优选模块取得这些照片的 `id` 后，调用：

```http
PUT /api/media/trips/{trip_id}/selected-photos
Authorization: Bearer <MEDIA_API_TOKEN>
Content-Type: application/json

{"batchId":"selection-2026-09-28-01","source":"photo-selection","photoIds":["<photo_id_1>","<photo_id_2>"]}
```

`GET` 同一路径返回当前清单、`updatedAt` 和按提交顺序排列的 `photos` 元数据。尚未提交时返回空清单，`batchId`、`source`、`updatedAt` 为 `null`。`PUT` 是整份替换，不是追加；空数组表示清空。相同 `batchId`、`source` 和有序 `photoIds` 重试不会更新时间。新批次替换后，被移出清单的照片不能继续调用精修接口，已经保存的版本不会删除。

`batchId`、`source` 必须是 1–128 字符的字符串；`photoIds` 必须是无重复的照片 ID 数组，最多 10000 张。所有 ID 必须已上传且属于路径中的行程；无效或跨行程 ID 整份请求返回 400，不写入部分结果。行程不存在返回 404，缺少或错误的 Bearer 令牌返回 401。请求不包含文件路径。

## 精修

所有接口使用 `Authorization: Bearer <MEDIA_API_TOKEN>`。`photo_id` 必须处于当前优选清单中；不存在返回 404，未优选或已被移出清单返回 409。

DGX 视觉建议通过 OpenAI 兼容的聊天接口工作：

- `DGX_VISION_BASE_URL`：默认 `http://127.0.0.1:18192/v1`（Spark 上 vLLM 听 8192，由 `spark-tunnel.sh` 转发）
- `DGX_VISION_MODEL`：默认 `qwen38-27b`，对应服务端 `--served-model-name`，对不上会 400
- `DGX_VISION_TOKEN`：可选；仅在模型服务启用鉴权时设置
- `DGX_VISION_TIMEOUT`：默认 180 秒。实测一次建议 100.3 秒，写死 90 秒会时好时坏

这四个变量由 `pyserver/media/vision.py` 统一解析，照片选优的打标（`vlm`）用的是同一份默认值，两边不会各指一个模型。选优侧想单独覆盖，另设 `PYSERVER_VLM_BASE_URL` / `PYSERVER_VLM_MODEL` / `PYSERVER_VLM_API_KEY` / `PYSERVER_VLM_TIMEOUT`。

| 接口 | 请求 | 成功响应 |
|---|---|---|
| `POST /api/media/photos/{photo_id}/develop/suggest` | 无请求体 | `params`（裁切及曝光、对比度、饱和度、锐度、高光、阴影、gamma）、`rationale`、`cropReason`、`model`、`elapsedMs`、`events` |
| `POST /api/media/photos/{photo_id}/develop/preview` | `{"params": {...}}` | 临时 JPEG 字节，不保存 |
| `POST /api/media/photos/{photo_id}/develop/review` | `{"params": {...}}` | `approved`、`note`、`model`、`elapsedMs` |
| `POST /api/media/photos/{photo_id}/develop/save` | `{"params": {...}, "note": "可选"}` | `variant` 和更新后的 `photo` 元数据 |

`suggest` 发送原图给私有隧道内的视觉服务；`review` 用同样参数生成临时预览，再把原图和预览送去复核。模型超时、连接失败、结构化输出无效时返回 503，参数越界返回 400。`save` 不覆盖原图，每次产生新的 `develop-*` 版本；下游可使用 `GET /api/media/photos/{photo_id}?variant={variant}` 获取其 JPEG 字节。

视觉建议请求使用 `temperature=0.1` 和 `max_tokens=6000`，为支持较长视觉推理的模型保留足够输出空间，同时让参数建议更稳定；预览复核使用 `max_tokens=300`。建议参数还包括八个 HSL 色彩通道和 5 点 master RGB 曲线，由服务端确定性应用。两者都要求模型最终返回结构化 JSON。

安装独立的 [mcp_images](https://github.com/timaliev/mcp_images) 后，启动前设置 `MCP_IMAGES_COMMAND=mcp-images`，或把它安装在项目 `.venv` 中由 `start.sh` 自动检测。上游包即使使用 Pillow 后端也需要 ImageMagick 动态库；macOS Homebrew 安装后，`start.sh` 会设置 Wand 所需路径。服务端只调用工具清单中名称精确匹配的 `raster_crop` 和 `raster_adjust`，用受控临时文件路径映射照片 ID，且不把用户或模型提供的文件路径传给工具。缺少所需工具、参数无法映射、子进程退出或超时时，预览和保存会返回明确错误。当前适配器已在上游 `1.3.1` 上实测。

`mcp_images` 是独立的 MIT 许可项目，不将其源码复制进本仓库。项目自有的 Pillow LUT 只补充高光和阴影曲线；原图保持只读，每次保存产生新的照片版本。
