# 架构与按需加载

## 目录边界

| 目录 | 职责 |
| --- | --- |
| `src/` | 网页入口、状态与三个独立视图；`shared/` 只提供纯数据和规划规则 |
| `ios/TravelMemory/` | SwiftUI 客户端，规划页的地图、交通、住宿与每日行程各自成组件 |
| `server/http.mjs` | HTTP 协议、输入限制与跨域响应 |
| `server/config.mjs` | 读取与原子写入私有 `config.yml`；只向网页返回密钥配置状态和优先级 |
| `server/agent.mjs` | 单次规划的状态创建、确定性兜底与最终响应 |
| `server/agent/` | 模型循环、工具定义、执行器、输入清洗、行程校验与能力状态 |
| `server/agent/tool-handlers/` | 按地点、交通、住宿、草拟、行程补充划分的工具实现 |
| `server/providers/` | 高德、道旅、Duffel、OTA CLI 的独立适配器与可用状态 |
| `server/ota/` | 飞猪、途牛各自的 CLI 调用和共享结果归一化 |
| `server/media/` | 按需加载的私有照片 API、去元数据、分析、修图、本地 MiniMax H3 视频任务 |
| `shared/` | 网页与服务端共享的地点目录、记忆归一化、行程规划算法 |

## 规划时的加载顺序

1. `model-loop.mjs` 根据当前状态从 `definitions.mjs` 选择本轮可用工具。模型开始时只看到需求确认、出发地和地点发现；取得地点后才看到交通与住宿；完成这些查询后才看到草拟工具；草拟成功后才看到景区产品、餐饮和地面交通工具。未提供给本轮模型的工具调用会返回 `tool_not_loaded`。
2. `tools.mjs` 只负责调用上限、缓存、耗时记录和错误边界。真正执行时，它动态导入 `tool-handlers/` 中对应的实现。
3. 工具实现通过 `providers.mjs` 调用供应商。该入口只预先导入轻量的可用状态；实际需要高德、道旅、Duffel、OTA 或 12306 MCP 时才动态导入适配器。需要凭据的供应商若未配置凭据，会直接返回空结果，不导入其适配器。
4. OTA 适配器在查询时分别动态导入飞猪或途牛模块，再调用相应 CLI；模型上下文里只有本项目当前阶段的高层工具定义，不包含所有供应商 MCP 的工具定义或原始响应。
5. 模型不可用或没有完成草拟时，`agent.mjs` 使用相同的工具执行器完成确定性流程，并在 `agentRun.status` 标明降级。
6. `/api/media/` 请求才导入 `server/media/`；视频任务实际创建时才读取 Spark 上的 ComfyUI 工作流。媒体数据和工具定义不进入外部 Step 模型上下文。

`GET/PUT /api/settings` 管理 Step Plan 和供应商密钥，以及航班、火车票、景点门票的数据源顺序。每次规划读取一次配置快照；供应商仍并行查询以展示全量候选，推荐项先按来源顺序，再按报价与行程条件选择。首选来源没有有效候选时回退。`config.yml` 不提交到仓库，写入权限为 `0600`。

供应商返回值先由适配器规范化，再经工具实现校验，最后通过 `plan-output.mjs` 校验行程和能力状态。网页与 iOS 消费同一 `/api/plan` 响应。

## 扩展位置

- 增加供应商：在 `server/providers/` 新建独立适配器，只从 `server/providers.mjs` 的对应调用点动态导入，并更新 `status.mjs`。不要把供应商原始工具定义直接加入模型上下文。
- 增加 Agent 工具：在 `server/agent/definitions.mjs` 定义契约与可用阶段，在 `tool-handlers/` 实现，并在 `tools.mjs` 注册动态导入。
- 调整规划规则：修改 `shared/planner.mjs` 与相应的 `test/` 测试；保持价格、评分、地点和路线的来源校验。
