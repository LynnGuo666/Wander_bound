# M03 有来源文字素材卡

`GET/PUT /api/media/trips/{tripId}/photos/{photoId}/material-card` 使用媒体鉴权。只允许当前行程选优清单内的规范化original，未入选/越行程/不可读均按M01合同拒绝。

PUT 请求：`{expectedVersion, fields}`。fields支持 `sceneDescription`（800字）、`subject`（300）、`place`（200）、`capturedAt`（100），每项 `{value, source:{kind,reference}}`。kind为user或documented_import，reference必须非空；未提供项明确value=null、source.kind=unknown。更新使用expectedVersion，冲突409。保存原图SHA，不从文件名猜测信息；原图更换后旧卡不能自动复用。

分镜提交将复制卡片与选优/原图快照。没有卡时只读取已有capturedDay并标upload_metadata，其余unknown；未合并选优分支的tags/EXIF不冒充已上线自动卡。文字卡及Step出站数据均不包含照片字节。上游d368f64的build_reel_assets目前仅作为后续映射参考，未合并。

人工验收四卡通过正式接口导入公开NPS来源描述；未知拍摄日期保留null，不能将此多日期集合描述为同一次旅行。见 `generated-evidence/m03/material-cards-api.json`。真实Step连通性调用成功，使用现有step-5-preview客户端、仅文字，见 `step-connectivity.json`；不是分镜效果验收。

当前本地实现b6a267c，Spark验证分支cf768f7、clean、11项定向测试通过；本地全量77passed。M01准入采用用户明确验收后继续的指示，仅豁免旧Session造成的终态等待，完整性缺口仍保留；业务模型/质量/确认门禁不变。
