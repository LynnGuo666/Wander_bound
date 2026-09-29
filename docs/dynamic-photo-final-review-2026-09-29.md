# 动态照片最终审查索引（2026-09-29）

隔离分支 `feat/dynamic-photo-ai-h3` 实现后端批次结算、画面分析和本地 H3 单图视频。旧主线、现行 Spark 服务和 preview 服务均未覆盖；本次没有修改 Web/iOS 页面。VibeHub 任务为 `task.ai-h3.d664bdd1c091`，完整 criterion 状态以 V3 lifecycle 为准。

## 运行与配置

- [集成/API 说明](dynamic-photo-integration.md)：从提交精选清单、`develop-batch-and-settle` 批次请求，到 job 状态轮询、照片关联、视频/封面鉴权读取、有限重试与不明 H3 提交状态恢复，含可运行请求示例。完整批次入口是唯一自动触发边界；逐张保存不会猜测最后一张。
- [来源与冻结契约](dynamic-photo-sources.md)：精修结算、输入字节快照、版本、跨行程校验和失败语义。
- [画面分析契约](dynamic-photo-selection.md)：现有视觉模型通路、schema、排序与 skipped 规则。
- [H3 工作流说明](dynamic-photo-h3.md)：`travel.minimax-h3.dynamic-photo.i2v@1.0.0`、比例画布、prompt/seed 和共享模型控制器。
- [Spark 真实验证报告](dynamic-photo-real-validation-2026-09-29.md)：部署隔离与恢复、素材许可和哈希、真实精修/AI/H3、耗时、ffprobe/完整解码、鉴权、重启与 skipped。逐项机器收据在 [JSON](generated-evidence/dynamic-photo-real-validation-receipt.json)；[密集帧联系图](generated-evidence/dynamic-photo-real-dense-contact.jpg) 供画面审查。

实证 MP4 私有副本保存在本机原控制根的私有 artifact 目录，SHA-256 `acbef4a8459207181e6834bdfb58e7cacbeba7d469f6cf418fd1c6cd8275a17c`，不提交 Git。拥有环境权限的维护者可用收据中的 job ID 和输出 hash 定位并核对私有文件。视频源于竖幅真实照片的非零精修版本，经真实 Qwen38 选择和真实 MiniMax H3 生成，非测试替身。

## 最终回归

在隔离工作树执行，Python 命令使用项目虚拟环境的解释器：

| 检查 | 命令 | 结果与日志 |
| --- | --- | --- |
| Python 全量 | `python -m pytest -q pyserver/tests` | 188 passed、25 warnings、7.73 秒；[日志](generated-evidence/dynamic-photo-final-pyserver-tests.txt) |
| Node 全量 | `npm test` | 28/28 passed；[日志](generated-evidence/dynamic-photo-final-node-tests.txt) |
| 应用构建 | `npm run build` | Vite 构建成功，2153 modules transformed、271 ms；[日志](generated-evidence/dynamic-photo-final-build.txt) |

Node 测试首次在默认沙箱中因既有测试绑定 `127.0.0.1` 遇到 `EPERM`，记录 V3 risk 后在获准的主机网络环境原样重跑通过。构建临时复用原控制根 `node_modules`（两处 `package-lock.json` SHA 相同），构建后已移除符号链接；未更新依赖锁文件。构建有 `lucide-react` 的 `use client` 指令提示，退出码仍为 0。iOS 未运行构建或测试；本次未修改 iOS。

## 审查门禁

- c01–c07 已有主会话逐项审查通过；本文件与最终三份日志供 c08 审查，不能代替 V3 `criterion_review`。
- V3 lifecycle 的 `findings` 当前为空；先前风险均有实际处置或验证结果，包括 Spark 认证恢复、传输改用等比小图、精修本地渲染器接线、GPU 独占恢复，以及上述 Node 沙箱端口限制。
- review 节点、AgentResult、Session 与最终完成提议仍按 V3 门禁办理；任务归档须用户在受信交互中明确确认。
