# 五风格手帐适配

实现：`pyserver/media/scrapbook.py`。这五份美术规则根据产品约束和用户参考独立编写，未读取或复制受限 skill 的提示词、代码或派生预设。每份有稳定 id、版本、完整 prompt 摘要、布局版本和推荐 seed。提交时应冻结整个预设，不在执行时重新查默认规则。

| id | 名称 | 核心视觉语言 |
| --- | --- | --- |
| watercolor | 水彩 | 透明叠色、渗色、纸颗粒 |
| papercut | 层叠剪纸 | 卡纸切边、纸层厚度、浅投影 |
| clay | 黏土 | 圆润实心塑形、指压痕、体积阴影，避免毛毡 |
| halftone | 网点漫画 | 墨线、平涂套色、圆形网点 |
| pixel | 像素 | 方形网格、阶梯轮廓、有限调色板 |

## 构图与测试

一张已选优规范化 original 生成一张完整横向 3:2 图片：左侧主体场景重绘，右侧同场景关键元素贴纸，纸底与底部留白。模型不写标题，后续产品 renderer 程序排版。贴纸数量随素材，不固定六枚。

本轮同图比较使用人工验收行程 `c2712842-c987-4347-938b-b6bc6fa7905e`、batch `m01-public-yellowstone-20260928-v1`、秋景 `199b155d-0c14-4673-8d25-5de27f175676`。来源及许可见 `validation-assets/m01-public-yellowstone.json`。五个请求由正式 selected-only redraw 接口进入共享 controller，详见 `generated-evidence/m02/preset-submissions.json`。这些是风格适配证据，独立手帐产品接口与标题验收另记。

M01 四项技术标准均 passed，用户明确确认 M01 通过并要求继续。M02 按原 gate 中的明确例外条款，记录终态等待的准入例外；VibeHub 旧历史 Session 缺口保留。事件 `evt.48f692bf-7a87-44ee-9772-285828299d1a`，gate 完成 `evt.3f6f2e1e-bf73-4630-b42f-e0df0dd1522c`。

## 当前基线影响

本地实施基线 `ddccf99`；Spark `f4aea97`，提交前 clean、队列 0；上游 main `24aae84` 未变。选优分支更新到 `d368f64`，新增 EXIF/quality/tags 和 `build_reel_assets`，保留显式 `batchId/source/photoIds` 清单提交。未合并该分支；M02 使用已经验证的原图与清单合同。M03 设计文字卡时需核对新分支映射，但不能假设它已部署。

## 实际观察

最终五张的哈希、job/prompt ID、seed、尺寸、耗时与主审观察见 `generated-evidence/m02/preset-review.json`。全部 1248×832，正式 API 读取成功。

水彩和剪纸首轮偏摄影纹理，保留 v1 原样；采用更简短、风格前置、简化形状的 v1.1 后，水彩山坡呈透明色块，剪纸山体/树木/云层有明确切边和纸层。黏土 v1 为圆润微缩浮雕，但颗粒仍较粗；网点 v1 墨线和印刷点可辨；像素 v1 方格与阶梯轮廓清楚。五张场景主体与金树/山/云贴纸可对应，无需云图片调用。预览应使用这批真实输出，不能拿用户参考图冒充。
