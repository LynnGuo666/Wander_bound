# 行驿 Travel Agent

旅行规划应用：React 网页、SwiftUI iOS 客户端、Python FastAPI 主服务，以及在 DGX Spark 上运行的 Node.js Docker MCP 数据适配器。

## 本地启动

1. 安装 Python 3.12+、Node.js 22+、npm 和 ffmpeg。首次运行会自动创建 `.venv`、安装 Python/Node 依赖并构建网页。
2. 在本机 `.env` 填写 Step Plan 和需要的供应商密钥；也可在应用设置页写入本机 `config.yml`。两者均不提交到 Git。
3. 保持 `./spark-tunnel.sh` 运行，使本机 `14176`–`14179` 连接 Spark 的四个 Docker MCP 服务。需要图片生成时另开 `./spark-comfy-tunnel.sh`。
4. 运行 `./start.sh`，打开 <http://127.0.0.1:4176/>。`GET /api/health` 检查主服务，`POST /api/capabilities` 展示 MCP `tools/list` 的实际能力。

Python 主服务只在本机调试；Spark 上运行 OTA、12306、道旅与旅行数据聚合四个 Docker MCP。Spark 的旧 Node HTTP/Agent 服务已停用。`./start.sh` 中的 API 地址可用环境变量覆盖，协作者只需要可访问的 MCP HTTP 地址，无须在本机运行供应商 Docker。

## 代码边界

| 目录 | 职责 |
| --- | --- |
| `pyserver/agent/` | Step Plan 流式 Agent loop、延续会话、懒加载工具、规划与降级处理 |
| `pyserver/api/`, `settings/`, `trips/`, `media/` | FastAPI 入口、`config.yml` 设置、行程记录、相册及本地媒体工作流 |
| `pyserver/providers/` | MCP HTTP 客户端与非 MCP 的高德 API |
| `server/ota/`, `server/providers/`, `server/mcp-data/` | Node 供应商解析与高层 MCP 工具实现；无主服务、Agent 或媒体 API |
| `deploy/*-mcp/` | Spark 上相互独立的 Docker MCP 容器 |
| `src/`, `ios/`, `android/` | React、SwiftUI 和 Android 相册上传客户端 |

数据路径：Python Agent → `travel-data-mcp` 四个工具 → OTA/12306/道旅 Docker MCP → 供应商。途牛三层信封与道旅 `hotelInformationList`/`price.lowestPrice` 都在 Node 层解析，Python 收到归一化结果。密钥通过仅供本次请求的 MCP HTTP 头发送。MCP 工具按需调用，Agent 输入不会一次包含所有供应商工具定义。

旧 Node 主服务保存在 Git 标签 `archive/node-server`，现在的 `main` 只保留 MCP 数据代码。架构细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，图片工作流见 [docs/MEDIA_ARCHITECTURE.md](docs/MEDIA_ARCHITECTURE.md)。

## 验证

```bash
.venv/bin/python -m pytest pyserver/tests -q
npm test
npm run build
```

`POST /api/plan/stream` 提供会话事件、工具调用与结果；`GET/PUT /api/settings` 管理密钥和来源优先级；`/api/trips` 保存行程与历史；`/api/media` 处理私有照片和回忆短片。真实供应商报价和订票链接以返回时的结果为准。
