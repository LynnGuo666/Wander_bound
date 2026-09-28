# 合并后从这里接手

本阶段 PR：<https://github.com/LynnGuo666/travel-agent/pull/2>。先读 [总交接](../delivery-handoff-2026-09-28.md)，再按下面步骤核对自己的环境。PR 合并不会自动部署 Spark，也不会复制私有媒体库或 VibeHub 控制状态。

## 1. 新 checkout 的基础验证

使用已合并提交新建开发分支，避免直接在部署分支开发。要求 Python 3.12+、Node.js 22+、npm、FFmpeg；Ubuntu/Debian 还需可显示中文的字体：

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-noto-cjk
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python -m pytest pyserver/tests -q
npm run check
```

macOS 可使用系统 PingFang；其他系统设置 `SCRAPBOOK_FONT_PATH` 为实际存在、覆盖标题字符的字体路径。代码会拒绝缺字或排队后已变化的字体，不会用乱码代替标题。CI 现已显式安装 `fonts-noto-cjk`；不需要 GPU 或供应商密钥即可跑上述测试。

本次复核修复 `4aa9658` 本地为 **84 passed**，包含缺字体错误经 contextlib 传播的反例。CI 状态以 PR Checks 当前 head 为准，不把旧提交的通过记录当作新提交结果。

## 2. 环境与现有服务

从 `.env.example` 配置自己的未跟踪 `.env`，或沿用授权获得的私有设置。不得从历史聊天、证据 JSON 或日志复制凭据。

| 配置 / 服务 | 用途与边界 |
| --- | --- |
| `MEDIA_API_TOKEN` | 私有媒体 Bearer 鉴权；没有令牌不能访问已有 job 和图片 |
| `MEDIA_STORAGE_DIR` / `TRIP_STORAGE_DIR` | 私有持久数据目录；仓库不包含已上传原图、服务端 job 数据或行程数据库 |
| `STEPFUN_API_KEY` / `STEPFUN_BASE_URL` | Step 文本分镜；保持 `step-5-preview`，默认只发文字素材卡 |
| `SPARK_QWEN_COMFY_URL` / `SPARK_QWEN_IMAGE_WORKFLOW_FILE` | 本地 Qwen 服务与 API 图 |
| `SPARK_COMFY_URL` / `SPARK_H3_WORKFLOW_FILE` | 本地 H3 服务与 API 图 |
| `SCRAPBOOK_FONT_PATH` | 可选字体覆盖；任务中固定路径/hash |

`./start.sh` 启动本机 API 与已构建 Web，默认 4176；它不安装模型。现有 Spark 服务在 `/home/Developer/travel-agent`，`travel-agent.service` 使用回环端口 4174；`deploy/spark/start-python.sh` 启用模型控制器，并覆盖 Comfy 地址为 Spark 的 8191/8188。不要把本机 API 与 Spark API 同时用于调度同一组 GPU 服务；真实生成统一通过 Spark 既有 API/共享 controller。

需要访问现有验收数据时，使用经核实的 SSH 接入和 `./spark-tunnel.sh`（本机默认 4175 → Spark 4174）。主机信任、SSH 权限、媒体令牌和 Step 账号需要由项目负责人安全交接；仓库不会提供这些凭据。开始前只读检查 API 队列、实际部署 SHA 与工作树，不主动重启或重新部署。

只读回读当前草稿示例（在调用环境中已安全设置变量）：

```bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${MEDIA_API_TOKEN}" \
  "${TRAVEL_API_BASE_URL}/api/media/storyboards/a2e67591-7d04-4b1f-a3cc-375d3e23ee13"
```

这是 Spark 现有数据 ID，新建空库不会存在。HTTP 404 时先核对连接的服务与数据目录，不能把仓库中的旧 job JSON 直接写入生产媒体库。合并后部署应逐文件核对与 Spark `6c5fc9b` 的差异，备份持久数据并按正式发布流程执行；本次 PR 没有部署这个动作。

## 3. 接着修改哪些文件

| 下一步 | 节点 / 代码入口 | 完成证据 |
| --- | --- | --- |
| 真实分镜编辑确认 | `node.m03.storyboard`；`pyserver/media/storyboards.py`、`storyboard_routes.py`；[接口](../storyboard-api.md) | 回读最新草稿、真实编辑、用户确认及不可变版本；不能自动替用户确认 |
| 接入 H3 每镜头任务 | `node.m03.shots`；`jobs.py`、`job_routes.py`、`comfy.py`、`workflow_versions.py` | 确认快照 → 真实逐镜头输出，稳定 UUID、失败/重启恢复；不把 prepared 当运行 |
| 编排合法音乐短片 | `node.m03.compose` / `review`；`jobs.py` 和 FFmpeg 编排 | 约四镜头、严格 16:9、合法音乐、帧数/时间戳/下载与观感记录 |
| Web | M04 baseline → gate → forms → results；`src/views/TripsView.jsx`、`MemoryView.jsx`、`src/lib/memory.js` | 手帐/视频独立入口与真实 API 闭环，现有运维页不计 |
| iOS | M05 完整节点见下方快照；`ios/TravelMemory/MediaClient.swift`、`MediaView.swift`、`MemoryView.swift`、`Models.swift` | 真实预览、分镜、任务恢复与保存分享；CI 编译不等于模拟器/真机使用验收 |

共用 `jobs.py`、DTO 与工作流配置由一个明确负责人集成；并行执行必须隔离 worktree，不让两人共用暂存区。M04/M05 前置不满足时只做允许的准备，改变并行顺序先更新正式计划。

## 4. 计划与资料都在哪里

- 六任务只读快照：[M01](v3-m01-snapshot.json)、[M02](v3-m02-snapshot.json)、[M03](v3-m03-snapshot.json)、[M04](v3-m04-snapshot.json)、[M05](v3-m05-snapshot.json)、[M06](v3-m06-snapshot.json)。包含节点 scope、依赖、criterion 与导出 revision；历史基线文字保留原样，执行时按总交接和最新事实复核。快照不是可导入事件，也不替代最新 V3 状态。
- V3 project：`project.travel-agent.c9c4dc1293865e91`，原 control root：`/Users/chenm0m/LocalRepo/travel-agent`。原 `.vibehub` 控制数据和个人 MCP 配置不在 Git 中。其他机器需获得同一控制面的受支持连接/迁移，不能在新 checkout 静默初始化第二套同名任务。无法连接时可读代码和快照，不能声称已写进度或完成任务。
- [五张用户视觉参考与哈希](../references/scrapbook-2026-09-28/manifest.json)现随 PR 交接，仅用于效果对齐，不是生成证据或可复制的受限 skill。
- 模型生成证据在 `docs/generated-evidence/`；可复用预览在 `public/scrapbook-previews/`。图片/视频已入 Git，不依赖 `/private/tmp`。
- 原始测试照片不在 Git，公共来源、源文件 hash 在 [素材 manifest](../validation-assets/m01-public-yellowstone.json)。优先访问现有 Spark 素材；需要新库时从来源下载、校验后走正式上传与 selected-photos 接口，新 ID 要写入自己的证据。
- `scripts/prepare_m01_validation_assets.py` 是旧部署上的专用导入脚本：默认锁定 `24aae84`，并依赖当时的本机临时 JPEG 与可信 SSH 连接。它不是新机器一键初始化器。不得为绕过检查而直接改预期 SHA；先审查目标版本、来源文件与导入范围。
- VibeHub 修复是另一个仓库的未完成工作，不在本 PR。其本地 worktree、未提交修复和门禁缺口见总交接；若要接该工作需另行交接该工作树，不能以此 PR 合并推断它已交付。

## 5. 首次接手的停止点

先验证 checkout/依赖/CI，再取得控制面和现有 Spark 的访问权限，回读最新分镜及 V3 节点。当前业务停止在 **draft v1，未确认、未提交 H3**。继续时开新 Session；旧分镜 Session 已关闭且节点 blocked，须通过受支持命令按真实条件恢复。旧 plan-only 完整性问题仍可能阻塞最终归档，代码合并不会修复它。
