# 动态照片：AI 选图契约

`DynamicPhotoSelector` 只处理已结算的动态照片任务，逐张通过 `DynamicPhotoSources.read_input` 读取并校验冻结的 JPEG。它不使用旧选优标签，因为标签可能属于精修前的原图。`run_managed(jobId)` 使用现有 `ModelController.use("chat")` 和私有视觉模型配置；集成节点把它接入自动工作流。本阶段无真实模型出站证据，真实 AI 选择留在 real-validation 节点验证。

每张图要求模型严格返回 `photoId`、`suitable`（布尔）、`score`（0–100 整数）、`reason`（短理由）和 `motionPrompt`（适合时才有）。分析器核对 ID、字段类型、长度与相互关系，未知/重复 ID、超时、HTTP 故障和非法 JSON 均让任务成为 `failed` 并保留诊断码；不会默认选择首张。全部候选都成功分析后按 `suitable`、模型分数降序和精选清单原顺序排位，最多选择一张。没有适合候选才记 `skipped`，理由为全批不适合。没有本地分数阈值覆盖模型的 `suitable` 判断。

模型提示词版本是 `dynamic-photo-selection@1`。它偏向水波、云雾、蒸汽和树叶的细微运动，要求主体、构图和镜头稳定；对近景人脸、多人合影和密集文字保守。持久化的每张分析包含冻结输入 SHA-256、理由、分数、运动描述，以及本地调用收据：本地 ID、配置模型、提示词版本、耗时。真实响应若提供模型 ID、完成 ID 或 `x-request-id`，经长度/控制字符校验后另存为 provider receipt。`configuredModel` 与 `observedModels` 分开，前者不冒充实测模型身份。任务记录不保存 base64 图像或原始模型响应。

每个任务有文件锁，跨进程重复调用不会重复推理；每张合法结果在下一张之前原子保存。进程中断后只复用模型/提示词版本与冻结输入 hash 完全一致的已保存结果。`selected`、`skipped`、`failed` 的重复调用直接返回原结果，失败重试须由后续集成节点提供显式有界入口。模型控制器无法提供服务时是 `VISION_UNAVAILABLE`，静态照片不受影响。

针对性验证：`pyserver/tests/test_dynamic_selection.py` 用本地 JPEG、可注入分析器及 MockTransport 检查精修像素来源、排序和同分规则、全不适合、非法结构/ID、超时、精选变更、进程恢复与并发复用，以及模型控制器不可用。测试替身不代表真实视觉模型推理。
