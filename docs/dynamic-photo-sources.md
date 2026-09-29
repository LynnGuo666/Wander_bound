# 动态照片素材结算契约

此阶段提供后端输入结算和持久快照。结算返回 `prepared`，AI 选图与 H3 执行由后续节点接入；`executionReady=false` 明确表示尚无视频。

## 调用顺序

1. 客户端或后端编排器先调用既有 `PUT /api/media/trips/{tripId}/selected-photos`，提交非空的 `batchId/source/photoIds`，再按需要逐张调用既有 `POST /api/media/photos/{photoId}/develop/save`。每次保存的精修版本带 `selectionBatchId`。
2. 全批精修操作结束后，读取当前 `GET /api/media/trips/{tripId}/selected-photos` 的 `batchId`、`updatedAt` 和有序 `photoIds`，调用 `POST /api/media/trips/{tripId}/dynamic-photo/settle`。`photos` 必须覆盖整份清单且顺序一致，每项明确 `developed` 或 `none`。`none` 只允许该照片没有已登记的精修版本；即使精修版本来自上一精选批次，只要它是最新有效版本，就必须使用 `developed`。

```json
{
  "batchId": "selected-batch-42",
  "selectionUpdatedAt": "2026-09-29T12:00:00+08:00",
  "photos": [
    {"photoId": "11111111-1111-4111-8111-111111111111", "status": "developed"},
    {"photoId": "22222222-2222-4222-8222-222222222222", "status": "none"}
  ]
}
```

响应 `202` 包含稳定 `id`、`status=prepared`、`sourceSnapshot` 和 `associations`。相同账号、行程、精选版本、结算及输入内容再次提交时返回同一任务。`GET /api/media/dynamic-photo/jobs/{id}` 只允许任务所属账号读取；其他账号与行程的资料不交叉读取。选片清单改变、错批次、未入选、重复或不完整清单会拒绝结算。

结算在逐张精修保存运行期间返回 `DEVELOPMENT_IN_PROGRESS`。服务在渲染前写入持久尝试标记，保存完成或正常失败后清除；若进程意外退出，结算返回 `DEVELOPMENT_INTERRUPTED`。所属账号可调用 `GET /api/media/trips/{tripId}/dynamic-photo/developments` 查看尝试编号；确认进程已退出后，调用 `POST /api/media/trips/{tripId}/dynamic-photo/developments/{markerId}/resolve`，提交 `{"batchId":"...","reason":"..."}`。恢复会留下私有审计收据，然后重新按实际结果结算；运行中的进程不能被此接口清除。中断不会自动当成无精修。

已结算的同一精选版本拒绝新的 `develop/save`，返回 `BATCH_SETTLED`。用户需要再次精修时，显式提交新的精选 `batchId`；无需启用动态照片结算的现有精修流程不会遇到此门禁。若精选批次在渲染期间改变，旧保存请求返回冲突，不会写入新批次。

## 冻结与恢复

快照记录完整精选清单/来源/时间/hash、结算 hash，以及每张照片的 `photoId/sourceVariant/variantCreatedAt/sha256/width/height`。结算优先采用 `developments` 里最新登记的精修版本，没有登记结果才使用规范化原图。声明存在的精修版本丢失或 JPEG 损坏时明确失败。结算把实际 JPEG 写入任务私有 `data/media/dynamic-photo/jobs/{jobId}/inputs/`；后续 `read_input` 从该副本读并核验快照身份、JPEG 完整性、尺寸与 hash。原照片路径在结算后被覆盖，不会改变任务使用的像素；若冻结副本损坏则失败。精选清单改变也使旧任务输入失效。

结算使用行程级文件锁和原子任务记录创建，跨进程与重启时保持相同任务 ID。来源阶段仅初始化 `photoId → sourceVariant → dynamicVersionId=null` 关联；AI 选择、动态版本写入、实际自动触发和视频/封面鉴权读取仍属于后续节点。既有 scrapbook/memory 的 `selected_original_snapshot` 保持只读原图规则。

本阶段验证：`test_dynamic_sources.py` 覆盖精修优先、旧批次精修、原图回退、在途/中断恢复、丢失/损坏、冻结副本、清单变更、线程与独立进程重复提交、重启复用和跨账号访问；同时运行 `test_photo_develop.py`、`test_generation_contract.py`，结果 **21 passed**。这些测试使用本地 JPEG 和 HTTP 内进程应用；没有调用真实视觉模型或 H3。
