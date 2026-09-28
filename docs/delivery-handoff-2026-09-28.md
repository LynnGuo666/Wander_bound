# 阶段交付与续做清单（2026-09-28）

2026-09-29 接手复核补充：PR 已成功提交为 [#2](https://github.com/LynnGuo666/travel-agent/pull/2)。新接手者先读 [合并后接手步骤](handoff/START_HERE.md)，其中包括环境配置、代码入口和六任务完整只读计划快照。

## 当前结论

按用户要求暂停业务开发，提交阶段 PR。**M01 公共基础、M02 五风格手帐已完成技术验证；M03 已实现分镜接口并生成真实 Step 草稿，尚未确认或生成完整短片；M04–M06 尚未实施。**

本文是交接快照，工作流事实仍以 VibeHub V3 为准。六个任务当前读取均为 `lifecycle_state=active / state=blocked`，共同存在旧 Session 完整性缺口；这与业务代码完成程度是不同维度。M01 已获用户明确验收，正常归档仍被工具门禁拒绝，不能写成已归档。M02 尚待用户最终验收。

## 任务进度

| 任务 / V3 ID | 已实现及真实证据 | 未完成事项 |
| --- | --- | --- |
| M01 `task.m01.931bf5bbc699` | selected-only original 资格、素材/工作流/seed 快照、共享控制器、有限重试与重启对账；真实 Qwen 图片及 H3 单镜头；四项 criterion passed | 历史 Session 修复后，执行正常完成确认与归档；用户已确认通过 |
| M02 `task.m02.1bfa059ca7f9` | 五种本地风格、独立手帐 API、可选程序标题、预览与下载；五风格真实样张和正式 API 重启恢复；四项 criterion passed | 用户验收与正常归档；Web/iOS 页面分别属于 M04/M05 |
| M03 `task.m03-step-h3.6281d9938b8d` | 基线与 gate 完成；有来源文字卡；Step 草稿、编辑、确认接口；一次真实四镜头草稿成功 | 真实草稿编辑与用户确认；确认快照到 H3 的独立任务；逐镜头生成与恢复；合法配乐、转场与最终成片；四项 criterion 仍 accepted |
| M04 `task.m04.2441633ab4e7` | 已规划；现有运维页不能算业务入口 | Web 独立手帐/视频入口、分镜编辑确认、进度、预览下载、错误/刷新恢复及真实接口闭环；三项 criterion accepted |
| M05 `task.m05-ios.de98a0ad8365` | 已规划；可复用本次真实风格预览素材 | SwiftUI 五风格、分镜、等待与结果体验、保存分享、权限与基本无障碍；实际构建及运行，明确模拟器/真机；三项 criterion accepted |
| M06 `task.m06.d8bc8656e4e9` | 已有 M01/M02 分项证据可复用 | 汇总代码/部署/模型版本，真实约四镜头短片、Web/iOS 完整闭环与最终用户验收；四项 criterion accepted |

依赖保持 M01 → M02/M03 → M04/M05 → M06。M02/M03 准入已在 V3 记录用户对 M01 的验收及继续指令，依据真实基础证据推进；该记录没有修复旧 Session，也没有降低 full 工作流等级。

## 本次代码与版本

- PR 分支：`feat/m01-local-generation-foundation`；阶段业务提交 `9173cde`，交接提交 `d6dc27a`；接手复核另补 `4aa9658`，修复 CI 字体依赖及异常 traceback 传播。该补丁未部署 Spark。
- PR 基线：`origin/main=24aae844e252fe7cd8606a8f25ede45b66990dc0`（提交 PR 前重新核对）。
- Spark 最近已验证部署：`6c5fc9b169e7acb69809ac42b393bab7ec5021ee`，部署收据记录工作树 clean。远端采用精确文件部署，提交 SHA 与本地不同；逐文件哈希见 [M03 部署收据](generated-evidence/m03/storyboard-deploy.json)。
- 最近草稿回读时共享队列为 0。暂停收尾不提交新推理、不重新部署。
- 选优分支最后核查为 `d368f648f8d5e010fe5c750b16845efcfdb7367b`，**未合并**。其 EXIF/质量/标签等能力不能当作当前已上线能力。
- 原有 `.gitignore` 修改、`docs/STATUS_AUDIT_2026-09-28.md` 保留在本地。首次阶段提交未包含参考图；接手复核已将 `docs/references/scrapbook-2026-09-28/` 五张图及 manifest 原样补入 PR，哈希全部一致。参考图是用户视觉目标，不能当生成证据。

主要入口与说明：

- [公共契约](local-generation-contract.md)、[M01 交接](local-generation-handoff.md)、[运行与恢复](local-runtime.md)、[本地工作流](local-workflows.md)。
- [手帐 API](scrapbook-api.md)、[风格预设](scrapbook-presets.md)：`POST /api/media/scrapbooks`、`GET /api/media/scrapbook-styles`，任务查询/结果/图片/缩略图/重试见接口文档。
- [有来源文字素材卡](material-cards.md)、[分镜 API](storyboard-api.md)：`POST/GET/PUT /api/media/storyboards` 及独立 `/confirm`、`/retry`。
- M01 通用 generation-jobs 的旧 prepared DTO 仍是基础接口；客户端应接独立业务入口，不能把 prepared 当作已开始生成。
- [五风格真实预览清单](../public/scrapbook-previews/manifest.json)可直接供后续 Web/iOS 使用。

## 实际验证与产物

### 自动化检查

- 业务代码 `9173cde`：`.venv/bin/python -m pytest pyserver/tests -q` **83 passed**；接手复核补丁 `4aa9658` 新增反例后 **84 passed**，7 条既有 Pillow 弃用警告。
- PR 收尾：`npm run check` **16 个 Node 测试通过，Vite 构建通过**。首次受沙箱回环监听限制失败，允许本机回环后复跑成功；构建仍有依赖包 `use client` 指令警告。
- Spark 分镜部署定向测试 **12 passed**，详见部署收据。
- 首轮 GitHub CI 的 iOS 模拟器目标编译已通过；Ubuntu Python 测试因缺少中文字体失败（82 passed / 1 failed），已补安装 `fonts-noto-cjk`，并修复该错误暴露的 frozen exception traceback 问题。最新 CI 结果以 PR 当前提交 Checks 为准。
- 修复提交 `4aa9658` 的 [GitHub CI](https://github.com/LynnGuo666/travel-agent/actions/runs/36447615433) 两项均已通过：`web-and-api` 与 `ios-build`。
- 没有 iOS 模拟器交互或真机验收；CI 编译通过不替代真实模型或客户端业务闭环。
- 早期 runtime 文档的“72 passed”没有原始日志支持，已在 `ddccf99` 更正；对应 M01 handoff 的真实全量结果是 **71 passed**。

### M01 / M02 真实本地模型

- [Qwen 基础探针](generated-evidence/m01/qwen-probe.json)、[H3 cover 探针收据](generated-evidence/m01/framing-real-probe.json)、[真实 H3 单镜头 MP4](generated-evidence/m01/framing-cover-probe.mp4)。
- H3 cover job：`ad2e7823-3ecb-4de0-b1d4-e15312ef6da5`，引擎 1024×576、24 fps、124 帧；应用合成 125 帧。白边已消除，原图上下合计裁去约 11.98%。这是基础单镜头，不能计作 M03 完整旅行短片。
- [五风格观感与版本记录](generated-evidence/m02/preset-review.json)，以及 [v1.1 实际模型结果](generated-evidence/m02/preset-results-v11.json)。水彩和剪纸首轮效果不足，已修订并实际重跑；最终五风格均为 1248×832。
- [正式手帐接口结果](generated-evidence/m02/product-results.json)：中文标题 `9b1609cb-362b-433e-9479-1610e02f0869`、英文标题 `e3af1e3e-31db-4fa5-8a92-d5ec92f6c8ff`、无标题 `e6c0c55c-2eea-462d-91bd-37fb6fb2f99e` 均成功，图片与缩略图下载 HTTP 200、哈希一致。
- [正式手帐重启恢复](generated-evidence/m02/product-restart.json)：运行中重启 API 后保持同一 prompt UUID、attempt 和冻结快照，未重复提交。
- [响应丢失后对账成功](generated-evidence/m01/runtime-loss-accepted.json)、[结果不明时拒绝重投](generated-evidence/m01/runtime-loss-not-forwarded.json)、[重试上限](generated-evidence/m01/runtime-fault-cap-final.json)为已有真实恢复证据。

### M03 停留位置：真实分镜草稿

- job：`a2e67591-7d04-4b1f-a3cc-375d3e23ee13`，状态 **draft**，版本 **1**，标题 **黄石四季印象**。
- digest：`07d5676e57936df150fb5e91be6e68129ce15a14b3c427fdc1edfd7fcd914ad6`。
- [正式提交收据](generated-evidence/m03/storyboard-submission.json)、[真实草稿、出站文字与快照](generated-evidence/m03/storyboard-draft.json)。Step 仅收到文字素材卡，没有照片。
- 四镜头依次为秋景、河边麋鹿、大棱镜温泉、雪季瀑布；均缓慢推进，请求每段 5 秒，H3 帧网格映射为 124/24 ≈ 5.1667 秒。转场重叠会影响成片总时长。
- **没有对这份真实草稿执行编辑或用户确认，没有为它提交 H3。** 编辑/版本冲突/确认快照已有自动化测试，仍缺真实用户闭环。恢复时先 GET 最新状态，不能直接重用本文件中的版本和 digest 发确认。

### 验收素材

专用 trip：`c2712842-c987-4347-938b-b6bc6fa7905e`；selected batch：`m01-public-yellowstone-20260928-v1`，source：`manual-acceptance-20260928`。

| 图片 | photoId |
| --- | --- |
| 秋景 | `199b155d-0c14-4673-8d25-5de27f175676` |
| 河边麋鹿 | `5869d8f2-b80b-466a-a724-7f9702e0a3f0` |
| 大棱镜温泉 | `df012e97-1209-4270-9b6e-1e1f0d8267ee` |
| 雪季瀑布 | `a531f3cb-c2bb-439b-b1bb-04b97fa63dc0` |

作者、公共领域来源、哈希见 [素材来源卡](validation-assets/m01-public-yellowstone.json)。这是不同日期的人工验收集合，不代表同一次真实旅行或自动选优结果。original 指 MediaStore 规范化上传原图。M02 资格反例另上传了一张未入选副本，记录在 product-submissions；不应将它自动加入清单。

## 续做顺序与明确缺口

1. **M03 分镜**：回读正式草稿，完成真实编辑与用户明确确认；记录不可变确认快照，核验纯文字出站、错误与超时证据，再 review c01。
2. **M03 镜头**：实现确认快照到独立 video job 的映射，冻结每镜头 prompt/seed/workflow/时长。全部经共享 controller 调度真实 H3，复用有效镜头，验证失败、重试和重启恢复。视频不能依赖手帐产物。
3. **M03 成片**：处理 FFmpeg 时间戳和帧数、轻转场、封面与下载。基础 H3 AAC 有声音但来源未证，必须移除并换成有明确合法来源的统一音乐。现有默认同步会把 124 帧转成 125 帧；CPU 对照证明 passthrough 可保留帧数，见 [对照收据](generated-evidence/m01/handoff-ffmpeg-compare.json)。实现正式策略后验证播放、时长、严格 16:9 和观感。
4. **M04 / M05**：对应业务接口满足节点准入后分别联调 Web 与 SwiftUI；若要提前拆分手帐客户端工作，先正式调整计划与依据。素材资格、刷新/重开恢复、防重复提交及保存分享都需真实接口证据。
5. **M06**：复用同版本有效证据；补齐一支真实约四镜头 H3 短片、Web/iOS 闭环与恢复矩阵，再提请最终用户验收。

保留边界：五风格整场景重绘、同场景贴纸、纸底、3:2；标题由程序排版。手帐/视频独立，只用冻结 selected original。首版不扩多图拼页、独立贴纸导出、全功能编辑器或 App Store 发布。

## VibeHub 控制面与 Session 交接

- 六个 `session.plan-amend.t1.20260928` 至 `t6` 只有绑定、计划修改和解绑，从未 open，目前 unknown。现有 gap/recover 不适用，新建 Session 不能抹除缺口。
- 父任务的已关闭 Session 缺 progress；桌面完成路径曾绕过正规门禁形成 completed，这不表示历史已修复，也不能作为后续归档办法。
- M01/M02 正常完成提案被 `V3_COMPLETION_SESSION_GATE_FAILED` 拒绝。M01 用户确认保留有效，但不得伪造历史或降级绕过门禁。
- 本次执行 Session `session.m03.storyboard-main.20260928` 在用户暂停后记录真实结果并关闭，分镜节点保留未完成；不把暂停交接标成业务验收通过。后续应重新读取 V3，用新 Session 恢复工作。
- 所有本轮 Paseo 子会话此前已按用户指令归档，不再派工。

### 独立 VibeHub 修复候选（不属于此 PR）

用户仅授权先交代码和测试，未授权替换现用工具或应用真实历史。

- 工作树：`/Users/chenm0m/.paseo/worktrees/2ytf0t0p/v3-session-integrity-reconcile`。
- 分支：`fix/v3-session-integrity-reconcile`，候选提交 `2e6e4085e55be53130e7697a069468c7cad87c4a`。
- 独立审查发现通用 lifecycle 绕过、跨任务授权、跨任务同 Session 事件漏检、校验与追加竞态、过时完成摘要等边界。五个文件仍有未提交修复：`application.rs`、`event_store.rs`、`lifecycle.rs`、`views.rs`、`docs/v3/historical-plan-only-reconcile.md`。
- 修复后的专门反例测试和主审尚未完成；原提交测试通过不能代表未提交修复已验收。未安装、未部署、未修改真实历史。该工作树与修改需保留，之后单独审查交付。
- 支持任务 `task.session.9464640cdb64` 的后续审查 Session 状态需恢复时重新核查；归档 Paseo 窗口不等于自动关闭 V3 Session。

## 恢复前的最小检查

先读 AGENTS.md、V3 task_brief 与节点，再核对 Git 工作区、远端 main、Spark 实际 SHA、队列和现有 job。保护未提交用户文件；不要自动合并选优分支、重跑已成功模型或把本交接文件当作可写绑定。凭据继续由既有私有配置提供，不写入文档或 PR。
