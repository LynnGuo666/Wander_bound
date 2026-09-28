# Python FastAPI 主服务

`pyserver.app` 是唯一应用入口。各模块有独立目录和多个文件：

| 模块 | 职责 |
| --- | --- |
| `agent/` | Step Plan 流式 Agent loop、会话状态、工具编排、供应商发现、计划与降级 |
| `providers/` | MCP HTTP 客户端、高德非 MCP 查询；不解析供应商原始 MCP 业务信封 |
| `trips/` | 行程状态、历史和持久化 |
| `settings/` | `config.yml`、密钥和来源优先级 |
| `media/` | 私有照片、修图与本地 Qwen/MiniMax H3 作业 |
| `api/` | 健康、能力、规划流和网页资源 |

供应商 MCP 运行于 DGX Spark Docker。`TRAVEL_DATA_MCP_URL` 用于调用 Node 归一化工具；`TRAVEL_OTA_MCP_URL`、`TRAVEL_12306_MCP_URL`、`TRAVEL_DIDA_MCP_URL` 用于真实 `tools/list` 展示。Python 不运行 Docker，也不调用旧 Node `/api/data/*`。图片工作流经本地到 Spark 的 ComfyUI API 隧道调用。

本地运行 `./spark-tunnel.sh` 和 `./start.sh`。测试：`.venv/bin/python -m pytest pyserver/tests -q`。
