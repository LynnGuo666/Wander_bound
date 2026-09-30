# 行驿 · Wander Bound

**把美好装订成册。** Bind the Beautiful.

你去看世界，剩下的交给我。出发前，一句话得到有真实来源的行程；回来后，授权的照片在私有环境里变成一本属于自己的旅行手帐。

## 为什么做

旅行结束后，照片往往留在相册里，很少被重新整理。我们希望 AI 承担查证、选片、编排和生成的工作，让人把时间留给旅行，把决定权留在自己手里。行驿的核心是一份可以多年后再翻开的记忆；行程规划为它提供真实的时间和地点线索。

规划 Agent 遵守三条规则：

- **无感：**能从已有线索推断的先推断。只有缺少会改变路线的关键信息时才提问，并给出 2–5 个选项和“其他”。
- **在场：**交通、住宿和路线接入真实来源。没有核实到的价格或时长保持未知，不让模型补一个看似合理的数字。
- **有分寸：**服务端会增强景点、匹配餐饮、计算逐日时间线，必要时调整未锁定的末站；最终行程由人确认、修改或推翻。

这套设计来自十日谈里的两条主线：让记忆有依托，让 Agent 像管家。正式发布的[产品介绍](https://lynn-study.notion.site/3ea7a971191480c7843cf03d4b8c256e)和[技术架构解密](https://lynn-study.notion.site/3ea7a97119148023a470f3bb16ebe152)是对外口径；仓库内的[介绍文档](docs/PRODUCT_INTRODUCTION.md)与[技术架构](docs/ARCHITECTURE.md)用于随代码维护实现说明。

## 一次旅行的两条路径

| 阶段 | 行驿完成的工作 | 人作出的决定 |
| --- | --- | --- |
| 出发前 | Step Plan 编排任务；Travel MCP 接入交通、酒店与地点；高德提供地面路线；服务端校验来源和逐日可行性 | 回答真正影响路线的问题，确认或修改草案 |
| 回来后 | 从授权照片提取 EXIF、画质数值与本机视觉标签；重建旧旅程；精选照片并编排手帐 | 选择照片、修正历史证据、编辑并保留自己的页面 |
| 装订时 | Spark 上的 Qwen-Image 2.1 生成装饰素材，MiniMax H3 生成短镜头；任务落盘并可恢复 | 查看、调整和分享最终作品 |

照片原件和私有 EXIF 保存在用户的私有节点；对外图像会重新编码并移除 EXIF。外部 StepFun 接收规划需求及手帐编排所需的筛选后文字标签，不接收照片原件。供应商密钥随单次 MCP 请求的私有 HTTP 头传递，不进入模型上下文。更多边界见[技术架构](docs/ARCHITECTURE.md)和[媒体工作流](docs/MEDIA_ARCHITECTURE.md)。

## 一台 DGX Spark

Python 3.12 + FastAPI 是唯一应用主服务；Web 使用 React 19 + Vite，iOS 使用 SwiftUI，Android 使用 Kotlin。Node.js 22 的独立 Docker MCP 适配器对接交通与住宿供应商。Spark 使用单颗 GB10 和 128 GB 统一内存，运行本地视觉分析、Qwen-Image 2.1（INT8）和 MiniMax H3；Qwen3.8-27B（NVFP4，vLLM）作为独立本地对话能力，旅行规划默认仍由 Step Plan 驱动。

推理控制器根据模型租约、引擎队列、可用内存和压力决定加载、让位与恢复。手帐素材和短片进入持久化队列；默认夜间 23:00–07:00，且连续 30 秒检测到 CPU、内存压力、可用内存及可用的 GPU 活动信号满足空闲条件后才领取。忙时复查，重启后从落盘队列继续。交互式照片重绘即时处理。具体阈值与限制见 [Python 服务说明](pyserver/README.md)。

## 本地运行

1. 安装 Python 3.12+、Node.js 22+、npm 和 ffmpeg。首次运行会创建 `.venv`、安装依赖并构建 Web。
2. 在本机 `.env` 配置 `BOOTSTRAP_INVITE_CODE`、Step Plan 及所需供应商密钥；管理员也可以在设置页保存到本机 `config.yml`。不要提交密钥。
3. 保持 `./spark-mcp-tunnel.sh` 运行，将本机 `14176`–`14179` 转发到 Spark 的四个 Docker MCP 服务。需要媒体生成时另开 `./spark-comfy-tunnel.sh`。
4. 运行 `./start.sh`，访问 <http://127.0.0.1:4176/>。首次注册使用初始邀请码。除 `GET /api/health` 外，私有 API 均需账号会话。

Spark 生产部署由 `deploy/spark/travel-agent.service` 在 `127.0.0.1:4174` 提供 Web 和 API，并直连节点回环地址的 MCP 与 ComfyUI。本机可运行 `./spark-tunnel.sh`，从 <http://127.0.0.1:4175/> 查看 Spark 部署。iOS 访问私有 Spark 节点时需在同一 Tailscale 网络。

## 已发布的实测口径

| 场景 | 结果 |
| --- | --- |
| 旧相册重建 | 89 张照片，87 张有 GPS，聚类出 6 天行程 |
| 连拍选片 | 22 张中 20 张入选、2 张废片拦截、0 次处理失败 |
| 单张照片打标 | 78.3 秒 |
| 单图生成 | 26–41 秒 |
| 约 5 秒视频镜头 | 约 17 分钟；服务内存峰值约 42 GiB |
| 本地对话模型冷启动 | 320–400 秒 |

这些是[Notion 发布页](https://lynn-study.notion.site/3ea7a971191480c7843cf03d4b8c256e)中的具体测试记录，不是任何输入都能达到的性能保证。

## 代码导航

| 路径 | 职责 |
| --- | --- |
| `pyserver/agent/`、`pyserver/trips/` | 流式规划、会话记忆、真实地点约束、行程与时间线 |
| `pyserver/providers/`、`server/`、`deploy/*-mcp/` | MCP 客户端、供应商解析和独立数据适配器 |
| `pyserver/media/`、`pyserver/inference/` | 私有相册、手帐、视频、持久队列与 Spark 模型调度 |
| `src/`、`ios/`、`android/` | Web、iOS 和 Android 客户端 |
| `docs/` | [架构](docs/ARCHITECTURE.md)、[调度](docs/SPARK_INFERENCE_SCHEDULING.md)、[选片](docs/photo-curation.md)、[手帐](docs/JOURNAL_AGENT.md) |

## 验证

```bash
.venv/bin/python -m pytest pyserver/tests -q
npm test
npm run build
```

供应商报价、席位、可订状态随时间变化，展示时应以工具返回的时间和来源为准。旧 Node 应用保存在 Git 标签 `archive/node-server`；当前 `main` 的 Node 代码只负责 MCP 数据适配。
