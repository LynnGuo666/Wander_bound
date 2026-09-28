# M02 基线复核｜2026-09-28

本记录对应 VibeHub `task.m02.1bfa059ca7f9` 的 `node.m02.baseline`。计划状态与验收结论以 V3 事件为准。

## 版本与部署

- 本地实施分支 `feat/m01-local-generation-foundation` 为 `37ecdc75a5977974c44f43c76cf5ac1c2093d752`，其 M01 起点为 `24aae844e252fe7cd8606a8f25ede45b66990dc0`。本地 `origin/main` 仍指向 `24aae84`；本次没有 fetch、pull 或合并。
- 只读 SSH 在 Spark `/home/Developer/travel-agent` 核对到分支 `codex/m01-validation-20260928`、同一 `37ecdc75` 且工作树 clean。`localhost:4174/api/inference/status` 当次返回队列 0、image `ready`、video `stopped_on_demand`、chat `ready`、`loadingModel:null`。这只是瞬时健康与部署核对，不代表 M01 图片或 H3 视频生成通过；主会话正在统一运行真实 Qwen 探针，本节点不读其未发布结果。
- 历史 M02 baseline 记录的是 `4c31149`，旧原节点还引用 `0ee6531`。实际代码已加入 selected-original 契约、工作流快照及提交恢复机制；后续业务节点应以 `37ecdc75` 接口为起点，重新审视之后任何上游变化。

## M02 可接入的现有契约

- `pyserver/media/contracts.py:90-128` 从本行程已提交的 selected 清单冻结 `tripId`、`batchId`、`source`、`updatedAt`、完整 `photoIds`、清单哈希、输入 photoId 和规范化 JPEG original 的 SHA-256；缺清单、空清单、越行程、未入选与不可读原图明确失败。`original_from_snapshot` 在 `:131-145` 读取时再核对固定原图，不能改读 develop/AI variant。
- `pyserver/media/contracts.py:13-15,147-164` 已声明 `scrapbook`、`storyboard`、`video` 公共产品 DTO；`pyserver/media/jobs.py:94-104` 仅保存 `status=prepared`、`executionReady=false` 的输入契约。`pyserver/media/job_routes.py:73-105` 的 `POST /api/media/generation-jobs`、状态和结果接口已存在，但 result 在未生成时返回 409。M02 要新增真实手帐 runner、结果与状态闭环，不能把 prepared 当作可生成。
- 当前可运行队列的 `edit` 与 `memory` 分别是单图 Qwen 重绘和 H3 视频，并非手帐整页：`pyserver/media/jobs.py:55-92,238-335`。提交时冻结选优、工作流、参数与 seed；执行前重验原图及快照，先持久化 prompt UUID 再提交，恢复时查询同一身份。M02 需沿用其单 worker 与 controller，不把新 `scrapbook` 误送进现有 `edit/memory` 分支。
- Qwen 工作流 `travel.qwen-image-2.1.edit@1.0.0`、ComfyUI `0.37.0@4ef23c34`、前端 `1.53.6`；显式 `aspect_ratio=3:2` 时按 `contain-white-v1` 填入 1536×1024 输入画布。旧默认仍为 `source`，因此 M02 不能省略 3:2 请求或仅根据输入画布推断最终成图比例。快照 schema/哈希及旧参数语义见 `pyserver/media/workflow_versions.py:27-101,104-118`、`workflows/model-manifest.json:2-16`；API/UI 图见 `workflows/qwen-image-2.1-edit-{api,ui}.json`。M02 的 style/preset 版本、最终 3:2 拼版及标题绘制尚须独立实现。
- H3 工作流 `travel.minimax-h3.i2v@1.0.0`、ComfyUI `0.34.0@e80c1570`、前端 `1.51.9`，1024×576 / 124 帧 / 24 fps 为待真实探针确认的候选。模型/节点文件及参数见 `workflows/model-manifest.json:18-37`、`docs/local-workflows.md:7-36`。APP mode 官方最低前端 `1.41.13`，现装版本满足下限，真实 UI 导入与运行仍待核验。
- 推理控制 `pyserver/inference/routes.py:18-39` 中 warm 返回 HTTP 202；`pyserver/inference/controller.py:311-326` 暴露 `loadingModel`、`loadProgress` 和模型状态。202 表示开始预热，不表示模型已可生成。

## 参考与准入

已目视读取 `docs/references/scrapbook-2026-09-28/reference-01.png` 至 `05.png`，并逐一复核其 SHA-256 与 `manifest.json` 一致。五图都是“左侧场景重绘 + 右侧相关元素贴纸 + 浅色纸底 + 底部短文”的目标样式；01 为花店，02/03 为神社，04/05 为河畔城镇。它们不是已授权原始旅行输入，也不是本项目生成证据；五风格（水彩、剪纸、黏土、网点漫画、像素）的真实区分仍须以同一 selected 原图实测。

M01 V3 在本次读取时仍为 `active/blocked`，四项必需 criterion 均为 `accepted`，旧 `session.plan-amend.t1.20260928` 的 unknown 完整性缺口仍在。已有独立公开照片 selected 测试批次可供后续人工验收，但这不代替真实 Qwen 3:2、H3 动态镜头、快照/重启恢复、APP UI 实测或 M01 任务完成。`node.m02.gate` 应继续保持 planned，待 M01 交付与证据满足其 scope 后再启用。
