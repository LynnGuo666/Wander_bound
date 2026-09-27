# 旅忆 · 旅行规划 Agent

网页端与原生 iOS 客户端共享同一个规划 API。服务端使用 Step 5 Preview 的函数调用 Agent loop：解析需求、查询位置和供应商、提出地点组合、校验行程。五类能力是航班、景点、住宿、美食、地面交通探索；数据契约与当前边界见 [五类能力设计](AGENT_CAPABILITIES.md)。根据出发城市、位置、交通和酒店偏好、已到访记录生成深圳 1–7 天行程。相册与回忆视频属于后续阶段。

## 本地启动

需要 Node.js 22 或更新版本。网页与 API 在本机分别使用 `5173` 和 `4174` 端口。

```sh
cd travel-agent
npm ci
cp .env.example .env
npm run dev
```

打开 `http://localhost:5173`。直接输入“我想去深圳玩 3 天”，填写出发城市，或允许浏览器定位。无供应商密钥时仍可用内置的深圳地点资料规划；飞猪 CLI 可在受限体验模式查询机票、火车票和景区，遮蔽价格会记为空值，班次时刻仍可查看。酒店报价和评论在未获授权时显示为未获取。定位坐标只有配置高德 Web 服务 Key 后才能在服务端反查出发城市，因此也可以直接填城市。

`npm test` 运行规划算法与 Agent loop 测试，`npm run build` 构建网页。API 健康检查为 `GET http://127.0.0.1:4174/api/health`，规划接口为 `POST /api/plan`。请求包含 `query`、`destination`、`originCity`、`days`、`startDate`、`memory`，可选 `location: {lat, lng}`。网页和 iOS 均只在设备本地保存记忆；规划时将记忆发送到你配置的 API 地址。

直接调试后端可运行 `npm run agent:cli -- "我想去深圳玩三天" --origin 上海 --date 2026-10-09`。加 `--require-model` 会要求本次由 Step 5 Preview 真正完成，否则以非零状态退出，适合密钥配置后的联调。

API 返回 `agentRun.status`：`completed` 表示 Step 5 Preview 完成行程草拟，`degraded` 表示模型失败后由确定性流程完成，`unconfigured` 表示未配置 StepFun Key。服务端始终补齐景区产品、餐饮和地面交通三步。`trace` 只记录工具名、成功状态和耗时，不记录用户坐标或密钥。每次请求最多 7 轮模型响应、14 次模型工具调用、2 次行程草拟；模型超时、限流和格式错误不会让服务端无限循环。模型只能提交地点 ID，价格、评分和地点内容必须来自供应商或本地目录。详细到访记录在服务端过滤，发送给模型的是可选新地点及排除数量。当前环境未提供 StepFun Key，真实模型调用尚待密钥配置后联调。

模型接入依据为[阶跃星辰官方 Chat Completions API 文档](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create)：模型 ID 固定为 `step-5-preview`，使用函数工具调用。单次模型调用最多重试两次限流或服务端错误；连续失败三次后冷却 30 秒，本次规划改走有标记的规则流程。无密钥时 `--require-model` 会立即失败，避免把规则规划误报为模型规划。

## 原生 iOS

客户端使用 SwiftUI、[SwiftUIX](https://github.com/SwiftUIX/SwiftUIX) 组件库、MapKit 和 CoreLocation，部署目标 iOS 17。需要 Xcode 和 XcodeGen：

```sh
cd travel-agent/ios
xcodegen generate
open TravelMemory.xcodeproj
```

选择 `TravelMemory` scheme 和 iPhone 模拟器运行。模拟器默认访问 Mac 的 `http://127.0.0.1:4174`；真机请在“来源”页填写你自己部署的 HTTPS API 地址。当前没有发布签名和 App Store 包。SwiftUIX 在 `project.yml` 中固定了已验证的提交，生成的 Xcode 工程也纳入仓库。

## 供应商接入

在 `.env` 中设置：

| 变量 | 用途 | 没有密钥时 |
| --- | --- | --- |
| `AMAP_WEB_KEY` | 位置反查、其他城市 POI、附近餐饮、步行与公交路线 | 深圳内置地点 + 直线距离估时；餐饮为空 |
| `DIDA_API_KEY` | 道旅酒店 MCP 搜索 | 酒店区域建议，无房价 |
| `DUFFEL_API_KEY` | Duffel 航班 offer 搜索 | 保留交通偏好，无机票报价 |
| `FLYAI_API_KEY` | 飞猪官方 FlyAI Skill/CLI；机票、火车、景区 | 可查询受限体验模式；遮蔽价格不入报价，保留班次 |
| `TUNIU_API_KEY` | 途牛官方 MCP CLI；机票、火车、门票 | 未认证时跳过途牛查询 |
| `TUNIU_USE_OAUTH` | 本机已有途牛 OAuth 会话时设为 `1` | 默认 `0` |
| `STEPFUN_API_KEY` | Step 5 Preview Agent loop | 明确标记 `unconfigured`，使用确定性流程 |
| `STEPFUN_BASE_URL` | 可选的 StepFun API 网关地址，默认官方 API | 使用 `https://api.stepfun.com/v1` |

途牛 `tuniu-cli@1.1.1` 与飞猪 `@fly-ai/flyai-cli@1.0.16` 已作为项目依赖安装。服务端只调用查询命令，不调用下单或支付命令。飞猪无 Key 的景区和机票体验查询已经实际返回数据；正式额度、完整价格与库存需配置 Key 后复核。途牛 CLI 已验证可启动，但当前没有 OAuth 会话或 Key，真实查询待认证。道旅返回的数据结构与报价含义需要在账号开通后核验。预订前必须在供应商页面验价。高德配置后逐段查步行或公交时间，并查询每天末站附近的餐饮 POI；失败时保留并标注估算，餐饮保持空白。地图上的连线只表示地点顺序，不是导航路径。

携程景区合作方、12306 官方接口和美团/大众点评评论 MCP 尚未取得面向本项目的只读权限。携程开放平台公开的是合作方 API，没有找到可直接供个人项目使用的官方景区 MCP；评论也不能把第三方爬虫当成官方数据源。途牛门票仅展示文档定义的「起价」及其对应团期，绝不当作出游日成交价。餐饮需要把位置、口碑和优惠分开处理；接入选择与许可问题见 [美食数据策略](FOOD_DATA_STRATEGY.md)。正式“货比三家”必须先取得多家授权并统一含税价格、房型、早餐、退改与库存条件；当前不会把不同条件的结果声称为可比的最低价。各平台开放资格、公开费用和计算口径见 [数据接入调查](travel_agent_data_sources.md)。

## 隐私与运行边界

- 用户主动点击定位后才请求设备坐标。坐标和偏好用于本次规划；若配置高德 Key，坐标会发送至高德反查城市。
- 记忆保存在浏览器 `localStorage` 或 iOS `UserDefaults`，服务端不落库。服务器默认只监听 `127.0.0.1`。
- 深圳内置地点为编辑维护的起步目录，缺少实时营业时间、天气、门票和评论。餐饮建议依赖高德 Key，未知评分保持空白。
- 当前分别查询去程和返程机票、火车票；无兼容行程的返程报价不会被推荐。途牛火车只保留有余票的席别参考价；门到门总费用尚未接入。行程起始时刻在没有真实航班时属于规划假设。餐饮建议尚未占用游玩时间。iOS Look Around 的实景入口尚未接入。
- Spark 节点上现有 Laya 服务是另一个任务的模型部署；此项目不会把旅行记忆发送到现有的 BTC 模型。Step 5 Preview 通过阶跃星辰 API 或你配置的兼容网关调用，需单独评估数据传输与隐私要求。
