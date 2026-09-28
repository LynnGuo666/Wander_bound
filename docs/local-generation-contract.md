# 本地生成公共素材契约（M01）

本契约只建立选优输入资格、快照及独立产物 DTO。`scrapbook`（图片）、`storyboard`（分镜 JSON）和 `video`（视频）是三个不同的 `productKind`；完整生成流程由后续任务接入。当前 `prepared` 任务不会进入媒体 worker，也没有可下载结果。

## 输入资格

- `POST /api/media/generation-jobs` 需要媒体 Bearer token，JSON 仅接受 `productKind`、`tripId`、`photoIds`、可选 `prompt`。`productKind` 只允许 `scrapbook|storyboard|video`；scrapbook 恰好一张输入图生成一张图，storyboard/video 首版为 1–8 张不重复输入图。`photoIds` 顺序即实际输入顺序；`prompt` 非空时最多 4000 字符，超限直接 400，不截断。
- 服务端读取 `MediaStore.selection_record(tripId)`，要求已显式提交且非空。每个输入 ID 必须存在、属于本行程、列于这份选优清单，且 `original` 可读。这里的“可读”要求文件非空，Pillow 能识别为 JPEG 并完整解码；提交时及 worker 进入模型控制器前均核验。无清单/空清单不会回退到所有上传照片。`MediaStore original` 是上传后规范化的 JPEG，不保证保留手机原始 EXIF、RAW 或字节。
- 客户端不能传 `selectionSnapshot`、`inputVariant` 或其他额外字段。快照和哈希只能由服务端产生。旧 `memories` 和 `redraw` 入口复用同一资格规则；`redraw` 的 prompt 上限改为 4000，超限拒绝，不再静默截断。已有旅行、选优、精修 API 路由不变。

## 持久化快照

`selectionSnapshot` 随 job 私有 JSON 存盘，其结构为：

```json
{
  "schemaVersion": 1,
  "tripId": "<trip UUID>",
  "selection": {
    "tripId": "<trip UUID>",
    "batchId": "<提交批次>",
    "source": "<提交来源>",
    "updatedAt": "<提交时间>",
    "photoIds": ["<完整选优清单，保持提交顺序>"],
    "sha256": "<上述五字段规范 JSON 的 SHA-256 十六进制>"
  },
  "inputPhotoIds": ["<本任务输入顺序>"],
  "originals": [{"photoId": "<输入 ID>", "sha256": "<规范化 original 的 SHA-256>"}],
  "inputVariant": "original"
}
```

选优清单之后被替换，不会改变存盘快照，也不会导致运行时使用新清单或未入选照片。worker 在进入模型控制器前校验整个任务的输入顺序、快照和全部 JPEG 原图，且向生成服务上传每张图前重新核对内容哈希；删除、不可解码或内容变化会失败并记录 `errorCode`，不会改用 develop/AI 变体。即使旧任务已有 `promptId`，无快照的历史排队任务也会在控制器启动前失败。

## 独立产物基础接口

`POST /api/media/generation-jobs` 返回 201，包含 `id`、`productKind`、`resultKind`、`status="prepared"`、`executionReady=false` 和服务器快照。`resultKind` 分别为 `image`、`storyboard_json`、`video`。job 私有记录还保留 prompt、`backend=null`、`result=null`、`error=null`。`GET /api/media/generation-jobs/{id}` 返回状态与快照；`GET /api/media/generation-jobs/{id}/result` 在产物未生成时返回 409 `RESULT_NOT_READY`。后续 M02/M03 接入执行者时应从该持久化快照读取输入，再定义真实生成结果的存储及下载方式；不能把 `prepared` 解释为已排队或模型就绪。

请求错误放在 HTTP JSON 的 `detail: {code, message}`，资格错误返回 400/404/409；仅真实后端未配置的旧生成入口返回 503。核心错误码有 `SELECTION_MISSING`、`SELECTION_EMPTY`、`SELECTION_INVALID`、`PHOTO_IDS_INVALID`、`PHOTO_IDS_DUPLICATE`、`PHOTO_NOT_FOUND`、`PHOTO_WRONG_TRIP`、`PHOTO_NOT_SELECTED`、`ORIGINAL_UNREADABLE`、`ORIGINAL_CHANGED`、`SNAPSHOT_INVALID`、`REQUEST_INVALID`、`PROMPT_INVALID`。旧 job 状态增加 `errorCode` 字段，已有 `error` 文本保留。错误类型的 retry 路由在修改 job 前核对存在、类型和 failed 状态，不能排队另一类任务。

当前节点的验证使用临时合成 JPEG、内存 HTTP 客户端和替身生成适配器；它不代表真实 Qwen/H3 生成、模型工作流、视频合成或重启恢复验收。
