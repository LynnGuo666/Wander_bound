# 动态照片：后端批次入口与结果接口

## 从真实精修批次自动启动

客户端先通过既有 `PUT /api/media/trips/{tripId}/selected-photos` 提交精选清单，再读取其 `batchId`、`updatedAt` 和完整有序 `photoIds`。精修批次使用新的后端编排入口：

```http
POST /api/media/trips/{tripId}/dynamic-photo/develop-batch-and-settle
Authorization: Bearer <account token>
Content-Type: application/json

{
  "operationId": "f8ed9640-0bc0-4b46-8eb3-47b8da2527f9",
  "batchId": "<selected-photos.batchId>",
  "selectionUpdatedAt": "<selected-photos.updatedAt>",
  "photos": [
    {"photoId": "<selected photo 1>", "action": "develop", "params": {}, "note": ""},
    {"photoId": "<selected photo 2>", "action": "none"}
  ]
}
```

`photos` 必须按已提交清单完整覆盖；`none` 表示本次不新增精修，若旧批次已有有效精修，结算仍优先使用最新精修。入口逐张调用现有真实精修渲染与 `MediaStore.save_develop`，全部完成后才调用来源结算并自动排入现有 `JobStore` 单 worker：冻结实际像素 → 私有视觉模型逐张判断/排序 → 最多一张 → 本地 MiniMax H3。没有人工目标或提示词字段。既有单张 `develop/save` 调用方也可在全部操作结束后调用 `POST /api/media/trips/{tripId}/dynamic-photo/settle`，该入口现在同样自动入队；逐张保存本身不猜测最后一张。

`operationId` 是请求方为整批生成的一次稳定 UUID。服务保存 payload SHA-256 和逐张完成收据；重复 ID 配不同输入拒绝。中途失败返回 `settled:false`、`completedPhotoIds` 和失败码，不创建动态任务；同请求恢复只处理未完成项。每张精修按 `operationId+photoId` 得到确定性 variant；即使崩溃发生在文件写入之后、元数据/批次收据之前，也核查已有文件并恢复同一版本。精选批次或 `updatedAt` 变化时明确拒绝，需发起新批次。已有精修结果缺失或损坏时不能静默回退原图。

可直接运行的请求顺序如下。先设置部署地址、自己的账户令牌、行程 ID，并安装 `jq`；`operationId` 和请求体文件在同批重试时保持原值。示例把前一张交给精修、后一张明确为无新增精修，其余照片也须逐张加入完整清单。

```sh
export BASE_URL='http://127.0.0.1:8000'
export MEDIA_TOKEN='<account token>'
export TRIP_ID='<trip UUID>'
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/trips/$TRIP_ID/selected-photos" > selected.json
export OPERATION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
jq --arg operationId "$OPERATION_ID" '{operationId: $operationId, batchId: .batchId,
     selectionUpdatedAt: .updatedAt,
     photos: (.photoIds | map({photoId: ., action: "none"}))}' selected.json > dynamic-batch.json
# 将需要真实精修的条目改为 {"photoId":"...","action":"develop","params":{},"note":""}。
curl -fsS -X POST -H "Authorization: Bearer $MEDIA_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @dynamic-batch.json \
  "$BASE_URL/api/media/trips/$TRIP_ID/dynamic-photo/develop-batch-and-settle" > dynamic-job.json
export JOB_ID="$(jq -r .jobId dynamic-job.json)"
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/dynamic-photo/jobs/$JOB_ID" | jq '{status,selection,error,result}'
```

批次端点按提交顺序严格比对整份 `photoIds`。为测试完整精修链路，把相应条目设为 `develop` 后再发送，不能在请求里指定要动态化的照片或视频提示词。

来源任务身份包含 owner、整份冻结素材快照、产品版本、视觉模型/选择提示词版本、H3 runner 版本和冻结 H3 工作流图/版本/hash。模型、图或输入变更会产生新任务 ID；运行时核对对应版本。`JobStore` 唯一 worker 在应用启动 `resume()` 时恢复 `queued/analyzing/selected/generating` 动态任务，并用同一个 `ModelController` 串行调度视觉和视频模型；动态路径没有额外 worker。
在 Spark 启用模型控制器时，视觉请求使用控制器当前 `chat` 服务的 `/v1` 地址；本地无服务管理模式仍使用既有 `DGX_VISION_BASE_URL`。两种环境都只将真实冻结图像发往既有私有视觉服务。

## 查询、播放与恢复

结算响应给 `jobId` 和实际状态。`GET /api/media/dynamic-photo/jobs/{jobId}` 返回任务、冻结快照、分析理由、排序和失败信息。`GET /api/media/photos/{photoId}/dynamic-photo` 返回静态回退地址、每次来源版本及动态版本关联；成功项的 `result.videoUrl`、`result.coverUrl` 指向受账户和行程鉴权的 MP4/JPEG 接口。视频与封面读取先检查持久 hash；其他账号/行程不可访问。

任务失败后 `POST /api/media/dynamic-photo/jobs/{jobId}/retry` 是唯一重试入口，最多三次，不换候选。若 H3 prompt 曾进入提交阶段，重试先查询同一 prompt ID 的队列/历史：运行/已完成则继续原 prompt，明确失败才可新建显式尝试；查询不可达或 prompt 缺失时拒绝盲目重投，保留照片、所选目标与失败诊断。成功、跳过及有效结果的重复请求直接复用，静态照片始终可读。

```sh
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/dynamic-photo/jobs/$JOB_ID" > dynamic-status.json
export PHOTO_ID="$(jq -r '.selection.selectedPhotoId // .sourceSnapshot.inputs[0].photoId' dynamic-status.json)"
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/photos/$PHOTO_ID/dynamic-photo" | jq '{photoId,staticUrl,versions}'
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/dynamic-photo/jobs/$JOB_ID/cover" -o dynamic-cover.jpg
curl -fsS -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/dynamic-photo/jobs/$JOB_ID/video" -o dynamic-video.mp4
# 只有 status=failed 时才发出下面的显式重试；同一 JOB_ID 和目标保留。
curl -fsS -X POST -H "Authorization: Bearer $MEDIA_TOKEN" \
  "$BASE_URL/api/media/dynamic-photo/jobs/$JOB_ID/retry" | jq '{status,attempt,error}'
```

如果重试返回 `H3_SUBMISSION_UNKNOWN` 或 `H3_RECONCILE_UNAVAILABLE`，先检查已保存的 `h3.promptId` 在 Comfy 队列/历史里的真实状态，并恢复原 prompt；不自动改用新 prompt 或第二名照片。需要排查的任务状态可通过受鉴权的 job 查询获得。

本地集成测试使用真实 MediaStore JPEG、HTTP 应用、同一 worker 的可注入模型替身与持久文件测试恢复/鉴权。它们不证明真实视觉质量、H3 运行、无音轨或完整解码；真实运行证据在 real-validation 节点生成。

## Spark 验证部署与回退准备

真实验证前再次只读核对远端 `travel-agent.service` 的 HEAD/工作树、持久媒体任务队列、模型服务/Comfy 队列和可用空间；baseline 的零排队只是当时时刻。测试代码放远端独立工作树，样本及动态结果放隔离媒体目录，以独立端口运行验证应用。现有 `ModelController.start()` 使用 `SPARK_MODEL_LOCK_FILE` 的跨进程非阻塞 `flock`；默认相对路径会让两个工作树各建一把锁，因此不能靠默认值同时启动两个 GPU 调度器。真实运行前必须复核远端有效锁路径，在确认 live 队列及 Comfy 队列均空后受控暂停现行应用 worker，让验证应用使用同一**绝对锁路径**独占 GPU 服务；若任何活跃任务或不能安全暂停，先停止测试并记录风险。回退时先停止验证应用、释放控制器锁，再恢复原 `travel-agent.service` 并核对健康和原队列。测试目录/媒体与现行部署分离，不覆盖私有媒体或共享工作流，不合并主线。真实运行记录部署 SHA、非敏感模型/工作流版本、暂停/恢复收据、任务输出及验证命令。
