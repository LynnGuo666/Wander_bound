# Step 5 Preview 接入核对

核对日期：2026-09-28。资料核对结束时间：2026-09-28（北京时间）。以下数值只取自 StepFun 官方文档，适用于 `step-5-preview`；`step-router-v1` 的特殊限制不适用于此模型。

| 项目 | 官方说明 | Python 服务端状态 |
| --- | --- | --- |
| 模型与通道 | 模型 ID `step-5-preview`；Step Plan Chat Completions 地址 `https://api.stepfun.com/step_plan/v1/chat/completions` | 一致，`pyserver/step.py` 固定模型 ID，默认使用该地址 |
| 上下文与输入 | 上下文窗口 1M tokens；最大输入 1M tokens | 由服务端模型提供；Python 请求没有设置模型上下文窗口上限。工具结果会按项目规则截到 20,000 字符；没有对 1M tokens 做过实测 |
| 输出 | 最大输出 64k tokens；`max_tokens` 省略时官方默认为不限制，由模型决定；输入与生成 token 总数仍受上下文窗口限制 | 已移除原先的 `max_tokens=4096` 请求限制；未把 64k 当作每轮必须生成的长度 |
| 工具 | 支持 `type: "function"` 的工具调用，返回 `tool_calls`，工具结果用 `role: "tool"` 和 `tool_call_id` 回传；内置 `web_search` 不支持 | 只发送函数工具，服务端执行后回传结果；移除了官方 Chat Completions 参数表未列出的 `tool_choice=required` |
| 输出与推理 | 支持流式输出；Chat Completions 可用 `reasoning_effort` 的 `low`、`medium`、`high`；推理内容通过 `reasoning` 字段返回，兼容格式可用 `reasoning_content` | 使用流式输出并读取两个推理字段；没有强制推理档位，沿用官方默认；`temperature=0.2` 在官方允许的 0–2 范围内 |
| 其他模型能力 | 输入支持文本、图片、视频；输出为文本；支持 JSON Mode、JSON Schema 和提示缓存 | 目前旅行规划请求只发送文本与函数工具，未接入多模态输入、结构化输出或显式缓存控制；不能把模型支持误写成应用已实现 |

官方依据：[模型规格](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview)、[Step Plan 推理模型接入](https://platform.stepfun.com/docs/zh/step-plan/integrations/reasoning-api)、[Chat Completions API](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create)、[工具调用](https://platform.stepfun.com/docs/zh/api-reference/tool-call)。

本次核对是文档与本地请求契约的对照。当前本机没有可用的 Step Plan 密钥，尚未进行真实模型调用，也不能据此声称已实测 1M 输入或 64k 输出。
