# Step 分镜草稿、编辑与确认

- `POST /api/media/storyboards`：`{tripId, photoIds}`，1–8张selected original，返回202。每张先通过material-card接口提供有来源的sceneDescription；缺失描述409，其余未知字段保持null。提交时复制清单、原图hash、文字卡和Step提示词版本。实际出站为两个纯文字message，不含照片、工具或本地图像替代调用。
- `GET /api/media/storyboards/{id}`：planning/draft/confirmed/failed、version、draftDigest、draft、素材快照及错误。Step采用既有step-5-preview流式客户端，收集最终公开JSON并本地验证；不保存/展示推理内容。
- `PUT /api/media/storyboards/{id}`：`{expectedVersion, draft:{title,shots}}`。保存后version+1、status=draft、清除当前确认。可以调整镜头顺序、prompt、motion和5–8秒时长；必须每图一镜，order从0连续，不能重复或引用未选图。
- `POST /api/media/storyboards/{id}/confirm`：`{version,draftDigest,confirmed:true}`，须用户明确确认。过期版本/摘要409，重复相同确认幂等。确认复制独立快照和sha256，历史confirmedVersions不随后续编辑更改。此接口不会提交H3。
- `POST /api/media/storyboards/{id}/retry`：仅failed，最多3次显式attempt。每次Step最多2次有界尝试，API重启中断planning时标失败，等待明确重试，避免重启自动重复付费调用。

镜头字段：shotId、photoId、order、role、durationSeconds、prompt、motion、transition。role为opening/environment/detail/closing；motion为static/slow_push/slow_pan_left/slow_pan_right；transition为cut/dissolve。H3 24fps支持帧网格，5–8秒按最近124/141/158/175/192帧规范化，响应同时显示frames/fps/actualDurationSeconds。默认5秒实际124/24=5.166667秒，成片还需扣除转场重叠，不承诺精确20秒。

本节点只负责文本分镜；视频任务、合法配乐与最终成片由后续节点接入，不能拿draft/confirmed当视频成功。任何未确认草稿都不得提交昂贵H3推理。
