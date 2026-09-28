# 独立手帐 API

所有接口使用现有媒体 Bearer 鉴权。`GET /api/media/scrapbook-styles` 返回五种 id/名称/描述/版本/hash/推荐 seed，不返回 prompt。

`POST /api/media/scrapbooks`：

```json
{"tripId":"UUID","photoId":"已选优照片UUID","styleId":"watercolor","title":"黄石的秋天","seed":2026092901}
```

`title` 可省略或空，最多32字符，无换行/控制字符；服务端检查本地字体能否显示每个字。`seed` 可省略（预设推荐值）；其他字段拒绝。始终读取本行程 selected original，不能指定变体或自造快照。返回202，`id/productKind=scrapbook/resultKind=image/status/executionReady=true/seed/selectionSnapshot`。

提交时持久化完整预设（含 prompt 与 hash）、工作流、参数、seed、素材快照、标题及字体路径/hash。任务执行时不重读默认预设；字体被替换则明确失败。标题不发送模型，由程序将完整生成画面等比缩小留出纸底标题区，保持最终3:2，无标题不添加占位文字。

- `GET /api/media/generation-jobs/{id}`：真实队列/加载/运行/完成/失败状态、进度标签（采样期间百分比为null）、错误码、风格/工作流版本与hash、seed、结果。
- `GET .../{id}/result`：成功后返回image结果合同，含像素尺寸、imageUrl、thumbnailUrl、sha256、title、styleId/styleVersion/presetSha256/seed；未完成409。
- `GET .../{id}/image` / `thumbnail`：受鉴权JPEG下载，未完成409，错误job404。
- `POST .../{id}/retry`：仅failed scrapbook，最多三次总attempt；结果未知409 `PROMPT_OUTCOME_UNKNOWN`，不换UUID盲重投。

运行复用现有单worker及image控制器。原始生成图片先原子持久化为job目录的`generated.jpg`，再执行CPU标题与缩略图处理；重启可复用已有图，不重新请求GPU。选优快照/原图资格仍在恢复前核验。模型输出不是3:2则失败，不能拉伸伪装通过。

旧 `POST /api/media/generation-jobs` 保留 M01 prepared DTO语义，已有prepared任务不会因部署自动开始。正式客户端手帐入口使用上面的独立POST；视频和分镜继续各自实现。

常见错误仍为 `{"detail":{"code":"...","message":"..."}}`：素材沿用M01；新增 `STYLE_INVALID/TITLE_INVALID/TITLE_FONT_UNAVAILABLE/TITLE_FONT_CHANGED/OUTPUT_ASPECT_INVALID/PRESET_SNAPSHOT_INVALID/JOB_NOT_RETRYABLE/RETRY_LIMIT_REACHED`。部署字体默认优先Noto Sans CJK，也可通过 `SCRAPBOOK_FONT_PATH` 配置。

## M04 / M05 接入交接

代码提交 `1072a17`；Spark 验证分支 `b02d340`（逐文件对应见 `generated-evidence/m02/deploy-retry.json`）。真实样式预览位于 `public/scrapbook-previews/`，manifest 关联具体本地生成job/预设版本/hash与公开原图出处，供 Web 直接引用、iOS 作为包内资源；它们不代表任意输入的确定效果。

客户端只从正式 selected 清单选一张图，选择 styleId 并输入可选短标题，然后POST独立手帐接口。保留job ID；查询时展示progressLabel，百分比null时使用不定进度。成功后取result的imageUrl/thumbnailUrl并带同一媒体鉴权下载；iOS保存/分享使用下载后的本地文件。不要通过prepared DTO启动业务，不把手帐结果作为视频输入。

真实验证：本地全量75passed；Spark定向23passed。正式任务中文/英文/无标题均成功；对应成图见 `generated-evidence/m02/product-*-image.jpg`。三张1248×832，缩略图480×320，HTTP200与磁盘hash一致。API重启后运行中的剪纸prompt UUID未改变，attempt始终1；selected清单也未变。真实未入选409、非法style/title400、排队释放409已留收据。五风格适配证据与本轮产品API证据分别保存，不把Mock测试称为真实模型。

限制：黏土样张有较粗颗粒；模型对复杂输入的贴纸分布不保证固定数量。标题字体以本机可读字体为准，已冻结hash，不能静默替换排队字体。M02技术criterion已通过，任务归档仍受旧plan-only Session完整性缺口限制。Web与iOS入口验收属于M04/M05，尚未完成。
