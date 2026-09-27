# 旅行 Agent 的五类入口

用户只需给出一句需求，例如“从我现在的位置去深圳玩 3 天，选便宜的白天航班，不去上次玩过的地方”。Agent 将同一次规划拆成五项可追溯能力；界面可把它们呈现为五张卡片，底层共享同一份行程和记忆。每张卡片都应有 `已核实 / 无结果 / 未配置 / 查询失败` 状态，不能把模型生成的文本当成供应商报价。

## 执行顺序与数据契约

```mermaid
flowchart LR
  A[用户需求、位置与本地记忆] --> B[出发地与日期]
  B --> C[航班规划]
  B --> D[景点发现与去重]
  D --> E[住宿区域和酒店]
  C --> F[按时间与地点 ID 草拟行程]
  E --> F
  F --> G[附近餐饮]
  F --> H[逐段地面交通]
  G --> I[校验并返回五张能力卡]
  H --> I
```

| 入口 | 用户能看到什么 | 依赖与校验 | 当前数据来源 |
| --- | --- | --- | --- |
| 航班与火车规划 | 去返程候选，含价格、币种、时刻、经停/席别；避开红眼与隔夜 | 定位反查或手填出发城市；返程保留游玩与转场时间；税费、行李与席别未统一前只并列展示来源 | 飞猪 FlyAI Skill/CLI 已可体验查询；途牛 MCP CLI 待认证；Duffel 可选 |
| 景点规划 | 每天已核实的地点、地图坐标、景区产品；游玩时长与时刻没有真实来源时显示未核实 | 模型只能选择工具返回的地点 ID；排除已到访；门票起价必须保留对应团期，遮蔽价格不参与比价 | 高德 POI；飞猪 Skill/CLI、途牛 MCP 只读门票查询 |
| 住宿规划 | 推荐住在哪个区域、品牌偏好、酒店候选与报价含义 | 根据景点分布选区，再按品牌、总价和距离排序；供应商真实价格和预算分开显示；预订前重新验价 | 道旅 RollingGo 酒店搜索（2026-09-28 实测核验 `hotelInformationList`/`price.lowestPrice` 结构）；无密钥时只建议区域 |
| 美食规划 | 每天末站附近的餐厅、距末站的近似距离、供应商评分和人均；有照片时标为“地点照片” | 当前用高德餐饮类 `050000` POI；每家店只能安排一次，过滤已到访店，限制距末站 2 公里，结合评分、绕路、菜系与预算排序；未来用授权的美团/点评数据核实营业、评论与优惠 | 当前为可选高德 POI；美团/点评合作权限待确认，详见[美食数据策略](FOOD_DATA_STRATEGY.md) |
| 交通的实景探索 | 机场、住宿区域和景点之间的步行/公交时间、步行距离、线路和上下车站；iOS 可在有覆盖时查看沿途街景 | 路线分段必须来自路径规划服务。地点照片不能冒充街景。实景影像以 iOS MapKit Look Around 的实际场景可用性为准，未获得场景时显示路线文字/地图 | 可选高德路线；Look Around 客户端能力待接入 |

## Agent loop 的边界

Step 5 Preview 直接接收用户原始提示词，自行理解城市、日期、总天数、预算和必须停留日期。需要澄清时调用 `ask_question`，界面底部浮出常驻提问条，提供模型生成的选项和“其他”自由输入；确定后调用 `set_trip_spec` 提交约束。后续按阶段可见的工具为 `resolve_origin → discover_places → search_transport → search_stays → draft_plan → search_attractions → search_dining → explore_ground`。服务端校验约束和地点来源；模型不可用时明确标记规则流程。Step 请求使用流式输出，公开说明逐段展示；工具调用在参数流结束后执行。每次请求最多 200 轮模型响应、200 次模型工具调用、2 次草案。跨城火车票通过社区 12306 MCP 查询直达与中转，并展示逐段席别和换乘；它不是铁路官方维护的 MCP。

`POST /api/plan` 的新增字段：`returnFlights`、`trains`、`returnTrains`、`recommendedOutboundFlightId`、`recommendedOutboundTrainId`、`recommendedReturnFlightId`、`recommendedReturnTrainId`、`attractionOffers`、`returnFlightEarliestAt`、`dining`、每天的 `diningSuggestions`、`groundJourneys`、`providerStatus.dining`、`providerStatus.ground`，以及按五类组织的 `capabilityStatus`。其中 `offers_found` / `schedules_found` / `places_found` / `routes_found` 分别表示取得数字报价、仅有班次、地点和路线；`area_only` 表示只有区域建议；游玩时长与转场时间没有真实来源时为空并标注未核实，不做估算；`unavailable` / `empty` / `failed` 分别表示未配置、已查询无结果、查询失败。`groundJourneys[].imagery.status = "check-on-device"` 只表示客户端可尝试请求，**不表示街景已经存在**。`agentRun.trace` 可检查实际调用了哪些能力。

## 下一步实施

1. 途牛已配置 Key 并于 2026-09-28 用真实返回核验机票、火车与门票；道旅 MCP token 同日核验酒店搜索。仍待办理：高德（地点链路硬依赖）、飞猪正式 Key、Duffel（另需城市→机场码数据源）。
2. 比价时统一舱位、行李、税费、退改、酒店房型与早餐；当前飞猪票价未明确包含税费，标为待核，不与含税总价直接声称同条件最低。
3. 申请美团/点评消费者侧的只读餐饮数据权限，并核实展示与费用条款；将餐厅营业时间、预约和用餐时段纳入时刻表，再算餐厅至下一站的路线。当前餐厅是“附近建议”，尚未占用行程时间。
4. 在原生 iOS 客户端用 `MKLookAroundSceneRequest` 按每段路线坐标查询场景；只在返回非空场景时显示实景入口。网页端先展示地面路线详情。
5. 在供应商覆盖不足时保留未知项与来源状态，让用户修改目的地、日期或偏好后重新规划。

## 官方接口依据

- [高德 POI 搜索：周边检索、餐饮类型、评分、人均和照片](https://developer.amap.com/api/webservice/guide/api/search/)
- [高德路径规划：公交换乘、步行距离、上下车站](https://developer.amap.com/api/webservice/guide/api/direction)
- [Apple MapKit Look Around 场景请求](https://developer.apple.com/documentation/mapkit/mklookaroundscenerequest)

- [途牛官方机票、火车票与门票 MCP 文档](https://open.tuniu.com/mcp/docs/)
- [飞猪官方 FlyAI Skill/CLI 命令和返回字段](https://github.com/alibaba-flyai/flyai-skill)
