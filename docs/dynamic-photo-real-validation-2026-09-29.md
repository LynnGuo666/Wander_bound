# 动态照片 Spark 真实链路验收

脱敏的逐项运行收据见 [dynamic-photo-real-validation-receipt.json](generated-evidence/dynamic-photo-real-validation-receipt.json)。它记录固定代码 SHA、来源图 hash、模型响应 receipt、工作流快照、视频 hash、接口状态和回退状态；不含令牌、照片字节或模型原始响应。以下结论来自 2026-09-29 在 Spark 上的新批次运行，与本地替身测试及旧视频探针分开。

## 固定运行边界

- 隔离代码：`feat/dynamic-photo-ai-h3@1b489d0`，由 Git bundle 从本地隔离分支传入独立验证目录。现行部署代码 `8144c0f` 未覆盖，preview 服务未修改。
- 2026-09-29 14:01 CST，在现行媒体 jobs 无排队/运行、preview jobs 为空、H3 服务 inactive 后，暂停现行 `travel-agent.service`，验证服务在私有端口启动，使用与现行服务相同的绝对模型控制锁。验证服务 PID 1347159 持有该锁。守护 shell 的 EXIT/HUP/INT/TERM trap 与 40 分钟 systemd timer 都调用恢复脚本；测试结束先停验证服务再恢复现行服务，并复查健康、队列、锁。
- 验证账户、行程、媒体、任务与证据均在 clone 的 `private-evidence/` 私有目录。令牌文件仅用于隔离 HTTP 请求，不写入本报告、仓库或模型输入。实际运行节点仅有现有 `JobStore` 单 worker 与 `ModelController`。

## 真实照片和精修

| 候选 | 公有来源与许可 | 原文件 SHA-256 | 等比验证副本 | 验证副本 SHA-256 |
| --- | --- | --- | --- | --- |
| Yosemite Falls | [NPS 瀑布照片，公有领域](https://commons.wikimedia.org/wiki/File:Yosemite_National_Park_(30025981065).jpg) | `7a73ef31c51c6b239ec775e51d53e1cec08dca52aac551de7670d8e9af927f27` | 768×1007 JPEG | `9ffe5795b520cb8a9a196a489c22e104fc77f5e45a0e47246b7df798f13763f3` |
| EAP 标牌 | [实拍文字标牌，作者放弃权利并标记公有领域](https://commons.wikimedia.org/wiki/File:EAP-NHS-Sign.jpg) | `4b18f3d526913f744e3081610c738f4b23f740e2dc21d49eef3152939379037a` | 768×576 JPEG | `a8e532d9a5e953269a0e88ff40259f718153f22880d8719caaa9362c95f17081` |

完整精选清单经 `/api/media/trips/{tripId}/selected-photos` 提交。随后只调用 `develop-batch-and-settle`：瀑布照片使用 `pillow-local@1` 执行曝光 `0.28`、对比度 `1.08`、饱和度 `1.04`；标牌明确为 `none`。瀑布原图落盘 SHA-256 为 `4a2f6840de95df2e83a011a1a50cba5c84e25398404df04e11fc5c101ed75401`，精修版本 `develop-ca9602ccf3d4` 为 `d6226bded7280f0b0f67fb8753750dd690957d19abeaf0373352f9de1880ea9b`，尺寸保持 768×1007。实际像素的三个 RGB 通道平均绝对差分别为 27.513、26.781、23.861（0–255），中心像素从 `(165,166,170)` 变为 `(206,207,212)`；批次 receipt 和逐张元数据均记录渲染器版本。冻结快照里的瀑布输入 hash 等于精修版本，标牌输入 hash 等于上传后的原图，后续 AI/H3 读取同一冻结字节。

## AI 选择与 H3 执行

真实私有 `qwen38-27b` 对冻结的两张实际画面逐张分析：瀑布 `suitable=true, score=92`，理由是水流可做细微运动、岩壁/森林静止；标牌 `suitable=false, score=32`，理由是中心文字密集、缺少自然动态。两次服务响应均实际报告 `qwen38-27b`，模型请求分别耗时 14.966 秒和 11.632 秒，response ID 与输入 hash 在脱敏收据中。模型自动选择精修瀑布；生成英文运动描述要求瀑布持续轻微流动、底部少量雾气，岩壁和森林保持稳定。请求未提供人工目标或视频提示词。

H3 prompt `252f9f91-2008-410f-9dff-f0de3ebcd75a` 于 14:03:20 CST 提交，并于 14:11:48 完成，提交到持久结果耗时 508.66 秒。冻结精修图 768×1007 映射到 512×672 画布，拟合 512×671、底部补 1 像素、相对比例误差 0.000992；Comfy 只有该 prompt 在运行，无待排队任务。安装的 ComfyUI 源码为 `e80c157`，冻结工作流 `travel.minimax-h3.dynamic-photo.i2v@1.0.0`，完整工作流 hash `62381c8c06402ce1e39b3175caf87b7c1a6cbac53a3395a7990246a5cb1d6a72`；UNet、文本编码器、视频 VAE 的实际模型文件名和字节数在收据中。固定 seed、prompt ID、工作流图和输入 hash 均持久化。

真实 MP4 的独立 `ffprobe -count_frames` 返回一个 H.264/yuv420p 视频流、512×672、124 帧、24 fps、5.166667 秒，没有音轨；独立 `ffmpeg -xerror` 全片解码无误，以 `-re` 实时速率播放式解码用时约 5 秒。MP4 SHA-256 为 `acbef4a8459207181e6834bdfb58e7cacbeba7d469f6cf418fd1c6cd8275a17c`。首/中/尾和[每 0.5 秒密集抽帧](generated-evidence/dynamic-photo-real-dense-contact.jpg)显示瀑布和底部雾气连续改变，岩壁与森林轮廓及构图稳定，未见明显换景或大幅形变；这是视觉抽样审查，不能量化所有可能的细微伪影。

成功版本 `68680deb-6363-5bfe-bbce-9192380429f3` 仅关联选中的精修瀑布。隔离服务内以 owner 令牌读取视频和封面均为 HTTP 200，下载 hash 与持久收据一致；照片关联返回相同动态版本及精修静态 URL。另一个账户的三项读取均为 404。重复提交同一 operationId/输入复用原成功 job，没有第二次 H3 推理。服务重启后新 PID 再次独占同一锁，成功结果、鉴权读取、关联、批次复用和下述 skipped 状态均保持。

仅标牌的新行程经同一完整 batch 入口得到真实 `skipped`：`qwen38-27b` 判 `suitable=false, score=28`，无 `selectedPhotoId`、无 H3 intent，也没有第二次视频生成。它证明无合适照片时保留静态结果。

14:17:54 CST，guard 停止验证服务并恢复现行 `travel-agent.service`：现行健康接口 HTTP 200、控制锁重新由现行 PID 持有，回退定时器 inactive；现行工作树仍 `8144c0f` clean，原 jobs 仍为 21 succeeded/2 failed/1 draft。preview 未修改。恢复后 H3 与 Qwen-Image Comfy inactive，Qwen38 active，无 GPU 视频队列任务。

## 视频取得方式与验收边界

私有可播放 MP4 已另存至本机原控制根的私有 artifact 目录，权限为仅所有者读写，SHA-256 与真实输出相同；没有纳入 Git。原文件及封面持久留在 Spark 的隔离验证目录。验证服务现已停止，公开仓库仅提供脱敏收据和联系图；拥有环境权限的维护者可用收据中的 job ID 与输出 SHA-256 核对私有文件。

对应正式验收：c04 的真实单图 H3、原比例、静音约 5 秒、完整解码和稳定主体；c07 的公有真实照片→真实精修→真实 AI 决策→真实 H3→鉴权关联/播放式解码、无合适 skipped、重启复用及现行服务回退。`docs/generated-evidence/dynamic-photo-*-tests.txt` 是本地替身/契约回归，不能代替这些真实模型证据。Spark 上的 FFmpeg CPU 对照短片为 125 帧、24 fps、5.208333 秒、无音轨并完整解码，只验证工具链，也不能代替 H3 输出。
