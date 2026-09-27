# 旅行 Agent 数据接入与“货比三家”预算

调研日期：2026-09-28。本轮资料核对结束时间：2026-09-28 06:43 CST。以下价格和资格以链接所指官方公开页面为准；没有公开单价的项目记为“待询价”，不能按免费预算。首版旅行应用代码位于 `travel-agent/`。飞猪官方 CLI 在无 Key 的受限体验模式可查询，途牛 MCP 查询需要 Key 或 OAuth；合作方 API 仍需分别授权。

## 当前代码接入状态

| 来源 | 实际调用 | 本机核验 |
| --- | --- | --- |
| [飞猪官方 FlyAI Skill/CLI](https://github.com/alibaba-flyai/flyai-skill) | `search-flight`、`search-train`、`search-poi`，经本地官方 CLI 调用 MCP | 景区和机票体验查询返回真实结构；火车返回班次但价格如 `2xx` 被遮蔽，仅展示时刻，不作为报价 |
| [途牛官方 MCP CLI](https://github.com/tuniucorp/tuniu-cli) | `call flight searchLowestPriceFlight`、`call train searchLowestPriceTrain`、`call ticket query_cheapest_tickets` | CLI 可启动；当前缺少 OAuth/Key，供应商查询未验通。火车只采用有余票的席别价；门票显示「起价」与对应团期 |
| [携程景区合作方平台](https://open.trip.com/ttd?locale=zh-CN) | 合作方 API；本项目未接入 | 未发现面向个人开发者的官方景区 MCP，需合作方权限 |
| [美团技术服务合作中心](https://developer.meituan.com/en-US/docs/biz) | 官网提供 MCP/Skill 入口，但未核实消费者评论只读工具 | 不把商户评分、餐厅 POI 或第三方爬虫文本冒充点评评论 |

## 接入清单

| 来源 | 比价所需数据 | 个人开发者 / 准入 | 公开成本 | 首版决定 |
| --- | --- | --- | --- | --- |
| [道旅 Dida 酒店 MCP](https://github.com/DIDA-AI/Dida-hotel-MCP-CN)（上游 [mcp.rollinggo.cn/mcp](https://mcp.rollinggo.cn/mcp)，另有免 Key 的 [rgh CLI skill](https://github.com/RollingGo-AI/rollinggo-hotel-skill-CN)，OAuth 登录） | 酒店、房型、实时报价、退改 | MCP token 已申请（2026-09-28 配置并实测） | 实测 `searchHotels` 返回 `hotelInformationList` 与 `price.lowestPrice`（如深圳南山酒店 1 晚 566 CNY）；商业条款仍需复核 | 酒店报价 A |
| [途牛 Agent 平台](https://open.tuniu.com/mcp/docs/) | 酒店、机票、火车、门票、度假 | 文档提供注册、申请 Key 和 CLI；个人资格需实测注册 | 未查到公开调用单价或免费额度 | 酒店报价 B，交通候选 |
| [飞猪 FlyAI](https://flyai.open.fliggy.com/docs) | 酒店、机票、门票、度假搜索 | [推广者入驻](https://flyai.open.fliggy.com/docs/partner)要求淘宝账号、年满 18 岁、实名及签署协议；可申请正式 Key | 未查到公开调用单价或免费额度；体验模式调用次数较少 | 酒店报价 C，仅对返回价格的结果参与排序 |
| [携程 / Trip.com 联盟](https://www.trip.com/partners/help/faq/account) | 目的地、酒店和机票跳转链接 | 官方明确接受个人站点、无需拥有网站 | 加入免费；[联盟链接](https://www.trip.com/partners/help/faq/tools)不返回结构化实时价格 | 作为第四个预订入口，不伪装成报价 |
| [Trip.com 合作方 API](https://developers.trip.com/) | 酒店、机票、火车、玩乐等 | 需合作方接入；[酒店接口自测页](https://apidoc.trip.com/apidoc/HAC/ToolViewer)要求携程提供 AllianceID/UserKey | 未查到公开调用价格 | 获批后增加报价来源 |
| [高德地图](https://developer.amap.com/api/mcp-server/summary) | POI、路线、天气 | 个人认证可用于非商业研究；对外商业运营应按[协议](https://developer.amap.com/pages/terms/)确认许可 | [定价页](https://developer.amap.com/upgrade)：个人非商业月配额 POI 搜索 5,000、基础 LBS 150,000；超额各 ¥30/万次。页面注明免费配额期限为注册认证起一年 | 国内路线与地点基础源 |
| [Apple Maps Server API / MapKit JS](https://developer.apple.com/maps/web/) | POI、路线、网页地图 | 个人可加入 Apple Developer Program | [会员](https://developer.apple.com/support/compare-memberships/) $99/年；会员内地图视图 250,000/日、服务调用 25,000/日，超限需申请提额 | 可作为网页地图选项，非商品报价源 |
| [Tripadvisor Content API](https://www.tripadvisor.com/business/solutions/hotels/content-api) | 地点、评论、照片、评分 | 自助注册，需信用卡和每日预算；酒店价格 API 另需申请 | 每月前 5,000 次免费；超额价格在结算页显示，未公开具体单价 | 境外地点与评论；不当作酒店价格源 |
| [美团生态开放平台](https://openapi.meituan.com/guide) / [企业版到餐 API](https://h5.dianping.com/app/bep-docs/sky-doc/canyinopenapi/daocan_api.html) | 餐饮商户、星级、人均、营业时间；旧企业文档列有评论与优惠接口 | 企业/第三方渠道需要分配凭据与权限；个人消费者应用能否获取点评内容待确认 | 未查到公开调用价格 | 高德发现候选；获授权后用美团/点评核实口碑、营业与优惠，见 [美食数据策略](FOOD_DATA_STRATEGY.md) |
| [美团技术服务合作中心](https://developer.meituan.com/en-US/docs/biz) | 官网称个人开发者可免费接入 MCP/Skills | 个人入驻入口存在；是否提供餐厅搜索、评论与价格需登录核实 | 首页称 MCP/Skills 免费接入，未公开具体餐饮接口价格 | 先做只读能力核验，不能把领券或导购 Skill 当作点评 API |
| [Booking.com Demand API](https://developers.booking.com/demand/docs/getting-started/prerequisites) | 酒店等库存与报价 | 必须先成为 Managed Affiliate Partner，签约后获得 Key 和 Affiliate ID | 未查到公开调用单价 | 获批后增加境外报价 |
| [Expedia Rapid](https://developers.expediagroup.com/docs/products/rapid/setup/getting-started) | 酒店报价及预订 | 合作伙伴接入 | 未查到公开调用单价 | 境外后续接入 |
| [Skyscanner Travel API](https://www.partners.skyscanner.net/contact/travel-api) | 实时航班报价 | 官方明确只面向商业合作；不接受非商业个人，通常要求月活至少 10 万 | 未查到公开调用单价；[联盟](https://www.partners.skyscanner.net/product/affiliates)另要求网站月独立访客超过 5,000 | 不列入个人开发者首版 API |
| [Duffel Flights](https://duffel.com/pricing) | 国际机票实时报价、下单 | 可注册按量使用，实际开通能力以账号为准 | 无预付费；确认订单 $3/单、Managed Content 1% 订单额、付费附加服务 $2/件；搜索:订单超过 1500:1 的超额搜索 $0.005/次 | 国际机票可评估；纯搜索产品需特别核算搜索费 |
| [12306](https://kyfw.12306.cn/otn/leftTicket/init) | 铁路官方车次、票价、余票 | 官网注明未授权其他网站或 App 开展类似服务；未找到面向个人的官方开放 API | 无可用公开 API 报价 | 用已授权供应商的火车查询，不抓取 12306 |

## “货比三家”的数据规则

1. 每次请求并行查询可用供应商。只将同一酒店、相同入住日期、人数、房型、早餐、退款条件和支付条件的结果放在同一比较组；不同房型或政策分组展示。
2. 比价字段保留 `provider`、供应商商品 ID、查询时间、币种、含税总价、税费明细、取消政策、库存状态、预订 URL。缺价格的结果标记“前往平台查看”，不填估算价、不参与最低价排序。[飞猪 FAQ](https://flyai.open.fliggy.com/docs/faq)明确部分商品不返回价格。
3. 报价有时效性。用户打开预订链接或下单前重新验价；供应商限制数据留存时按其协议处理。机票比较还需统一行李额、退改条件、是否中转和付款手续费。
4. 给每个适配器设置单独的调用次数、超时、错误率和月预算。某供应商不可用时，其卡片显示“本次未取到报价”，其余来源继续展示。
5. 地图、地点评论、供应商商品属于不同类别：高德、Apple Maps、Tripadvisor 不算酒店或机票的比价来源。

## 费用试算

假设每月 1,000 次完整行程规划，每次调用高德 4 次 POI 搜索及 2 次路线规划，并对每次酒店需求各向道旅、途牛、飞猪查询一次：

- 高德：4,000 次搜索和 2,000 次 LBS，落在个人**非商业且配额仍有效**的免费月额度内，按公开调用价计为 ¥0。若没有免费配额，同样的 6,000 次调用按 ¥30/万次约为 **¥18**；商业技术服务许可费用另计。
- 若规模升至每月 10,000 次规划且调用结构不变，高德 POI 搜索为 40,000 次，超出个人 5,000 次免费配额 35,000 次，按公开超额价约 **¥105/月**；20,000 次路线规划仍在 150,000 次月配额内。此例仍只适用于个人非商业、免费配额有效的条件。
- 道旅：按官方仓库声明，1,000 次搜索的调用费为 **¥0**；需在拿到 Key 后确认协议和实际限额。
- 途牛与飞猪：公开页面没有足够信息计算 1,000 次搜索的费用，故记为 **未知**，预算不能写成 ¥0。
- 携程联盟跳转：加入费用 **¥0**，但不产生可与前面三家排序的 API 报价。
- Tripadvisor：若每次规划调用 2 次 Content API，则月 2,000 次，在每月 5,000 次免费额度内；需绑卡，且这不是酒店报价 API。
- Duffel：若只查价不成交，搜索与订单比超过 1500:1 后会产生超额搜索费；以每月 10,000 次搜索、0 订单且全部搜索均计为超额的假设计算，约 **$50**，实际起算口径需向 Duffel 核实。

因此目前**不能给出“全部接入后的准确总价”**：途牛、飞猪、携程合作方、美团、Booking、Expedia 均缺公开单价或个人账号的实际授权条件。首版可先形成“道旅 + 途牛 + 飞猪”的酒店三家比较；后两家获 Key 并确认返回含税价格后才能把三家报价真正上线。申请时应询问：个人主体是否可用于对外网页、每月免费量、搜索/详情/验价分别如何计费、并发限制、缓存与展示许可、跳转或成交分佣。
