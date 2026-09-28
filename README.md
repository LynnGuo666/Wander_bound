# 行驿 Travel Agent

旅行规划应用：React 网页、SwiftUI iOS 客户端、Python FastAPI 主服务，以及在 DGX Spark 上运行的 Node.js Docker MCP 数据适配器。

## 本地启动

1. 安装 Python 3.12+、Node.js 22+、npm 和 ffmpeg。首次运行会自动创建 `.venv`、安装 Python/Node 依赖并构建网页。
2. 在本机 `.env` 填写 Step Plan 和需要的供应商密钥；也可在应用设置页写入本机 `config.yml`。两者均不提交到 Git。
3. 保持 `./spark-tunnel.sh` 运行，使本机 `14176`–`14179` 连接 Spark 的四个 Docker MCP 服务。需要图片生成时另开 `./spark-comfy-tunnel.sh`。
4. 运行 `./start.sh`，打开 <http://127.0.0.1:4176/>。`GET /api/health` 检查主服务，`POST /api/capabilities` 展示 MCP `tools/list` 的实际能力。

本机开发使用 `./start.sh` 和 SSH MCP 隧道。Spark 生产环境在 `127.0.0.1:4174` 运行同一个 Python FastAPI 服务，由 `deploy/spark/travel-agent.service` 启动；它直接调用节点回环地址的四个 Docker MCP 和两套 ComfyUI。`./start.sh` 中的 API 地址可用环境变量覆盖，协作者只需要可访问的 MCP HTTP 地址，无须在本机运行供应商 Docker。

## 代码边界

| 目录 | 职责 |
| --- | --- |
| `pyserver/agent/` | Step Plan 流式 Agent loop、延续会话、懒加载工具、规划与降级处理 |
| `pyserver/api/`, `settings/`, `trips/`, `media/` | FastAPI 入口、`config.yml` 设置、行程记录、相册及本地媒体工作流 |
| `pyserver/providers/` | MCP HTTP 客户端与非 MCP 的高德 API |
| `server/ota/`, `server/providers/`, `server/mcp-data/` | Node 供应商解析与高层 MCP 工具实现；无主服务、Agent 或媒体 API |
| `deploy/*-mcp/` | Spark 上相互独立的 Docker MCP 容器 |
| `src/`, `ios/` | React 和 SwiftUI 客户端 |

数据路径：Python Agent → `travel-data-mcp` 四个工具 → OTA/12306/道旅 Docker MCP → 供应商。途牛三层信封与道旅 `hotelInformationList`/`price.lowestPrice` 都在 Node 层解析，Python 收到归一化结果。密钥通过仅供本次请求的 MCP HTTP 头发送。MCP 工具按需调用，Agent 输入不会一次包含所有供应商工具定义。高德（POI、餐饮、路线）由 Python 服务直连，并内置免费配额 30% 的月度用量上限（POI 1,500 次、基础 LBS 45,000 次，见[价格页](https://lbs.amap.com/upgrade#price)）：计数持久化在 `data/amap-quota.json`、按自然月滚动，触顶后相应查询明确失败并在 `providerStatus` 标注原因，`/api/health` 的 `amapQuota` 展示当月用量。

旧 Node 主服务保存在 Git 标签 `archive/node-server`，现在的 `main` 只保留 MCP 数据代码。架构细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，图片工作流见 [docs/MEDIA_ARCHITECTURE.md](docs/MEDIA_ARCHITECTURE.md)。

## 验证

```bash
.venv/bin/python -m pytest pyserver/tests -q
npm test
npm run build
```

`POST /api/plan/stream` 提供会话事件、工具调用与结果；`GET/PUT /api/settings` 管理密钥和来源优先级；`/api/trips` 保存行程与历史；`/api/media` 处理私有照片和回忆短片。真实供应商报价和订票链接以返回时的结果为准。
