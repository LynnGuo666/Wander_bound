# 旅忆 · 旅行规划 Agent

网页端与原生 iOS 客户端共享同一个规划 API。服务端把用户自然语言原文交给 Step 5 Preview，由模型理解日期、跨城路线、预算和必须停留时段，并通过函数调用提交行程约束或追问用户。服务端校验约束并查询供应商。工具定义与供应商适配器按规划阶段和实际调用按需加载，结构见[架构说明](ARCHITECTURE.md)。五类能力是航班、景点、住宿、美食、地面交通探索；数据契约与当前边界见 [五类能力设计](AGENT_CAPABILITIES.md)。行程支持 1–21 天；火车票接入社区 12306 MCP 查询直达与中转。iOS 相册、私有图片处理、DGX Spark 本地 Qwen-Image-2.1 创意重绘和 MiniMax H3 回忆短片的架构见[媒体说明](MEDIA_ARCHITECTURE.md)，模型选型与下一步模块化设计见[媒体模型调研](MEDIA_MODEL_RESEARCH.md)。

## 本地启动

需要 Node.js 22.12 或更新版本；使用 nvm 时可运行 `nvm use` 读取 `.nvmrc`。网页与 API 在本机分别使用 `5173` 和 `4174` 端口。一键启动会检查依赖，首次运行时创建 `.env` 模板：

```sh
cd travel-agent
./start.sh
```

按 `Ctrl+C` 停止。网页默认打开 Agent Debug 工作台。需要真正的 Step 5 Agent 或实时供应商数据时，可在工作台填写单次请求密钥，也可在 `.env` 中配置服务端密钥并重新启动。

打开 `http://localhost:5173`。直接输入“我想去深圳玩 3 天”，填写出发城市，或允许浏览器定位。无供应商密钥时仍可用内置的深圳地点资料规划；启动 OTA MCP 后，飞猪可在受限体验模式查询机票、火车票和景区，遮蔽价格会记为空值，班次时刻仍可查看。酒店报价和评论在未获授权时显示为未获取。定位坐标只有配置高德 Web 服务 Key 后才能在服务端反查出发城市，因此也可以直接填城市。

## Agent Debug 与单次请求密钥

打开 `http://localhost:5173`，填写目的地、出发城市并点击「开始真实调试」。`POST /api/plan/stream` 通过 SSE 实时显示模型公开行动说明、每轮输入摘要、函数调用的参数和经过白名单筛选的返回值、请求内缓存命中、输入与输出 token、降级路径以及最终数据来源。没有模型密钥时，页面明确标记「模型未配置 · 规则规划」。执行记录是可验证的运行事件，不显示模型隐藏思维链；模型未提供公开说明时，界面只根据实际工具请求生成执行摘要并明确标注。

工作台支持按请求填写 Step Plan、高德、道旅、Duffel、途牛和飞猪密钥。密钥只在当前页面内存中，刷新即清空；服务端为每个请求创建独立的模型与供应商适配器，不修改全局环境变量。密钥不进入 Agent 输入、执行日志或浏览器存储。请只在本机 SSH 隧道、队伍 Tailscale 私网或 HTTPS 域名填写。生产环境先运行 `npm run build`，再运行 `node --env-file-if-exists=.env server/index.mjs`，前端和 API 使用同一端口。

`npm run check` 运行测试并构建网页，GitHub Actions 在推送和 Pull Request 时执行同样的检查，并构建 iOS 模拟器应用。API 健康检查为 `GET http://127.0.0.1:4174/api/health`，规划接口为 `POST /api/plan`，实时调试接口为 `POST /api/plan/stream`（SSE），二者仅接受不超过 256 KiB 的 JSON 对象。请求包含 `query`、`destination`、`originCity`、`days`、`startDate`、`memory`，可选 `location: {lat, lng}`。网页和 iOS 均只在设备本地保存记忆；规划时将记忆发送到你配置的 API 地址。

代码按用途分为 `src/`（网页）、`ios/TravelMemory/`（iOS）、`server/`（HTTP 入口、Agent loop、供应商适配器）、`shared/`（地点目录与规划规则）、`test/`（算法、供应商和 HTTP 契约测试）。`server/index.mjs` 只负责启动，`server/http.mjs` 可以独立测试请求处理。网页开发服务器通过 Vite 将 `/api` 代理到后端，因此本地不需要跨域配置。

直接调试后端可运行 `npm run agent:cli -- "我想去深圳玩三天" --origin 上海 --date 2026-10-09`。加 `--require-model` 会要求本次由 Step 5 Preview 真正完成，否则以非零状态退出，适合密钥配置后的联调。

API 返回 `agentRun.status`：`completed` 表示 Step 5 Preview 完成行程草拟，`waiting_for_user` 表示模型提出待回答问题，`degraded` 表示模型失败后由确定性流程完成，`unconfigured` 表示未配置 StepFun Key。`trace` 记录工具名、成功状态、错误代码、耗时和结果计数；`events` 记录可观察的执行过程和经过白名单筛选的工具输入输出，不记录用户坐标或密钥。每次请求最多 7 轮模型响应、14 次模型工具调用、2 次行程草拟；当前没有硬性 token 限额。模型超时、限流和格式错误不会让服务端无限循环。模型只能提交地点 ID，价格、评分和地点内容必须来自供应商或本地目录。详细到访记录在服务端过滤；外部 Step 模型会收到用户原始提示词、明确填写的表单字段和非敏感偏好，不会收到相册图片。

模型接入使用 Step Plan 的 `https://api.stepfun.com/step_plan/v1/chat/completions`，采用兼容 Chat Completions 的函数工具调用；模型 ID 固定为 `step-5-preview`。Step Plan 与普通开放平台 API 是不同的入口，需使用对应账户的 Plan 额度。当前没有可用 Plan 密钥，真实 Step 5 Preview 响应尚待联调。单次模型调用最多重试两次限流或服务端错误；连续失败三次后冷却 30 秒，本次规划改走有标记的规则流程。无密钥时 `--require-model` 会立即失败，避免把规则规划误报为模型规划。

## Spark 快速调试入口

在已经安装本机公钥的 Mac 上，项目根目录执行 `./spark-tunnel.sh`，打开 `http://127.0.0.1:4175/`。隧道通过组委会分配的公网 SSH `106.13.186.155:6082`，把本机 4175 转发到 Spark 上仅监听回环地址的 Agent `127.0.0.1:4174`；浏览器和 API 使用同源地址。保持终端运行，按 `Ctrl+C` 关闭；如果 4175 被占用，可运行 `SPARK_LOCAL_PORT=4176 ./spark-tunnel.sh`。私钥路径默认 `~/.ssh/id_ed25519`，可用 `SPARK_SSH_KEY` 覆盖。

此入口适合填写调试密钥。组委会的 7082 公网映射通向节点 7000 端口，目前没有在该端口开放无鉴权 HTTP 服务。队伍 Tailscale 地址 `http://spark-82.tailb7a50b.ts.net:7000/` 仍可供已加入 tailnet 的设备使用。

## 原生 iOS

客户端使用 SwiftUI、[SwiftUIX](https://github.com/SwiftUIX/SwiftUIX) 组件库、MapKit 和 CoreLocation，部署目标 iOS 17。需要 Xcode 和 XcodeGen：

```sh
cd travel-agent/ios
xcodegen generate
open TravelMemory.xcodeproj
```

选择 `TravelMemory` scheme 和 iPhone 模拟器运行。模拟器默认访问 Mac 的 `http://127.0.0.1:4174`；已加入本队 Tailscale 的真机在“来源”页填写 `http://spark-82.tailb7a50b.ts.net:7000`。其他部署使用 HTTPS。“相册”页按日期读取已授权照片，选中后才上传到私有媒体 API；媒体令牌保存在 iOS Keychain。Spark 部署和本地 MiniMax H3 工作流见[媒体说明](MEDIA_ARCHITECTURE.md)。当前没有发布签名和 App Store 包。SwiftUIX 在 `project.yml` 中固定了已验证的提交，生成的 Xcode 工程也纳入仓库。

## 供应商接入

在 `.env` 中设置：

| 变量 | 用途 | 没有密钥时 |
| --- | --- | --- |
| `AMAP_WEB_KEY` | 位置反查、其他城市 POI、附近餐饮、步行与公交路线 | 深圳内置地点 + 直线距离估时；餐饮为空 |
| `DIDA_API_KEY` | 道旅酒店 MCP 搜索 | 酒店区域建议，无房价 |
| `DUFFEL_API_KEY` | Duffel 航班 offer 搜索 | 保留交通偏好，无机票报价 |
| `TRAVEL_OTA_MCP_URL` | Docker OTA MCP 的内部地址 | 飞猪和途牛不接入 |
| `TRAVEL_12306_MCP_URL` | Docker 中社区 12306 MCP 的内部地址 | 不查询 12306 直达与中转车次 |
| `FLYAI_API_KEY` | 飞猪 FlyAI；机票、火车、景区 | MCP 可查询受限体验模式；遮蔽价格不入报价 |
| `TUNIU_API_KEY` | 途牛；机票、火车、门票 | 未认证时跳过途牛查询 |
| `STEPFUN_API_KEY` | Step Plan 的 Step 5 Preview Agent loop | 明确标记 `unconfigured`，使用确定性流程 |
| `STEPFUN_BASE_URL` | Step Plan API 地址；可按账户区域或兼容网关调整 | 使用 `https://api.stepfun.com/step_plan/v1` |

Spark 上的 OTA CLI 独立封装在 Docker MCP 中。服务端只发送结构化 `tools/call`，Agent 只能使用明确注册的只读查询工具，不能输入任意 CLI 命令。另一个容器固定安装 [`12306-mcp@0.3.10`](https://github.com/Joooook/12306-mcp)，它是社区实现而非铁路官方 MCP。两个容器的 Node 基础镜像均从 1Panel 的 `docker.1panel.live` 拉取，仅绑定服务器回环端口 `4176` 和 `4177`。部署或本地启用时运行：

```sh
docker compose -f deploy/ota-mcp/compose.yml up -d --build
curl http://127.0.0.1:4176/health
```

`POST /api/capabilities` 会连接 MCP 的 `tools/list`，返回当前工具名、说明和参数 Schema；网页「能力与数据来源」用表格展示这些实时元数据。途牛无 Key 时仍能发现本项目包装的工具，但查询需要认证。道旅有 Key 后才直接向上游 MCP 请求 `tools/list`。工具被发现不代表查询成功，表格另列本次实际结果数。飞猪无 Key 的景区和机票体验查询此前已返回数据；正式额度、完整价格与库存需配置 Key 后复核。途牛当前无 Key，真实查询待认证。道旅数据结构与报价含义需要在账号开通后核验。预订前必须在供应商页面验价。高德配置后逐段查步行或公交时间，并查询每天末站附近的餐饮 POI；失败时保留并标注估算，餐饮保持空白。地图上的连线只表示地点顺序，不是导航路径。

社区 12306 MCP 的车次、席别和中转结果仅作规划参考；余票与票价在预订前须到铁路官方核对。航班表格展示供应商实际返回的航司、航班号、机型、餐食、行李、税费与退改字段；供应商未提供的字段明确显示未知，不推断或编造。

携程景区合作方、12306 官方接口和美团/大众点评评论 MCP 尚未取得面向本项目的只读权限。携程开放平台公开的是合作方 API，没有找到可直接供个人项目使用的官方景区 MCP；评论也不能把第三方爬虫当成官方数据源。途牛门票仅展示文档定义的「起价」及其对应团期，绝不当作出游日成交价。餐饮需要把位置、口碑和优惠分开处理；接入选择与许可问题见 [美食数据策略](FOOD_DATA_STRATEGY.md)。正式“货比三家”必须先取得多家授权并统一含税价格、房型、早餐、退改与库存条件；当前不会把不同条件的结果声称为可比的最低价。各平台开放资格、公开费用和计算口径见 [数据接入调查](travel_agent_data_sources.md)。

## 隐私与运行边界

- 用户主动点击定位后才请求设备坐标。坐标和偏好用于本次规划；若配置高德 Key，坐标会发送至高德反查城市。
- 记忆保存在浏览器 `localStorage` 或 iOS `UserDefaults`，服务端不落库。服务器默认只监听 `127.0.0.1`。
- API 默认不向其他网页开放跨域访问。网页与 API 分域部署时，在服务端将 `CORS_ALLOWED_ORIGIN` 设为该网页的完整 Origin；同域部署无需设置。当前 API 没有用户认证或请求限流，不能直接作为公开服务暴露。
- 深圳内置地点为编辑维护的起步目录，缺少实时营业时间、天气、门票和评论。餐饮建议依赖高德 Key，未知评分保持空白。
- 当前分别查询去程和返程机票、火车票；无兼容行程的返程报价不会被推荐。途牛火车只保留有余票的席别参考价；门到门总费用尚未接入。行程起始时刻在没有真实航班时属于规划假设。餐饮建议尚未占用游玩时间。iOS Look Around 的实景入口尚未接入。
- Spark 节点上现有 Laya 服务是另一个任务的模型部署；此项目不会把旅行记忆发送到现有的 BTC 模型。相册图片与回忆视频只在私有媒体服务及本地 MiniMax H3 工作流处理；Step 5 Preview 通过阶跃星辰 API 或你配置的兼容网关调用，接收用户原始规划提示词、明确填写的表单字段和非敏感偏好。
