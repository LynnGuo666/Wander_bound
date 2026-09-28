# M01 公开真实照片验收批次

2026-09-28，在 Spark `24aae844e252fe7cd8606a8f25ede45b66990dc0` 建立专用 UUID 行程 `c2712842-c987-4347-938b-b6bc6fa7905e`，手工提交 `selected-photos` 批次 `m01-public-yellowstone-20260928-v1`，`source=manual-acceptance-20260928`。四张照片来自不同日期，**这是验收素材集合，不代表同一次真实旅行，也不冒充自动选优结果**。仓库只存来源、哈希和 HTTP 收据；JPEG 保存在 `/private/tmp/travel-public-fixtures/`，不纳入版本库。

| Commons page ID / 媒体 photoId | 人工素材卡 | 作者、来源与许可 |
| --- | --- | --- |
| `50246552` / `199b155d-0c14-4673-8d25-5de27f175676` | 秋季山地、金黄色树木；视线朝向 Yellowstone，适合检验地貌和季节色彩。 | Diane Renkin / Yellowstone National Park，2014-10-10；[Commons 来源页](https://commons.wikimedia.org/wiki/File:Looking_south_over_Yellowstone_from_Gallatin_National_Forest_(14924610824).jpg)标记 NPS 作品公有领域。 |
| `24352222` / `5869d8f2-b80b-466a-a724-7f9702e0a3f0` | 河边草地上数只麋鹿；历史胶片边框明显，适合检验动物主体保留。 | National Park Service Digital Image Archives，个人摄影者未标明、拍摄日不明；[Commons 来源页](https://commons.wikimedia.org/wiki/File:Yellowstone_National_Park_YELL4574.jpg)标记公有领域。 |
| `326389` / `df012e97-1209-4270-9b6e-1e1f0d8267ee` | 大棱镜温泉航拍，蓝色水体与橙色地热边缘清晰；适合检验自然纹理。 | Jim Peaco / National Park Service，2001-07（月）；[Commons 来源页](https://commons.wikimedia.org/wiki/File:Grand_prismatic_spring.jpg)标记公有领域。 |
| `50247083` / `a531f3cb-c2bb-439b-b1bb-04b97fa63dc0` | 雪季 Lower Falls 瀑布纵幅；适合检验水流和纵幅输入的留白策略。 | Jim Peaco / Yellowstone National Park，2014-04-03；[Commons 来源页](https://commons.wikimedia.org/wiki/File:Lower_Falls_of_the_Yellowstone_(13699489084).jpg)标记 NPS 作品公有领域。 |

完整来源卡、源 JPEG SHA-256 在 [manifest](m01-public-yellowstone.json)。[首次收据](m01-public-yellowstone-first-run.json)记录 TripStore.create、四次上传 HTTP 201、四次 `GET original` HTTP 200、selected PUT/GET HTTP 200 与规范化 original SHA-256。[复跑收据](m01-public-yellowstone-receipt.json)记录同一 trip/photo IDs 全部复用，`selection_updated_at` 未变化。源图与规范化 `original` 的哈希不同是预期结果：MediaStore 去 EXIF 并重新编码；纵幅瀑布还缩到了 `1707×2560`。

复跑：确认 Spark 部署 SHA 和已验证 SSH 控制连接仍有效，在仓库根目录运行 `python3 scripts/prepare_m01_validation_assets.py`。脚本先校验四张临时 JPEG 哈希及远端 clean/SHA，再从远端服务进程或配置读取媒体令牌，**只在 Spark 回环 HTTP 请求中使用，不打印或写入仓库**。它按规范化 original 哈希复用已导入照片，若既有清单不同则拒绝替换。部署或许可事实变化后先重审 manifest，不强行绕过检查。

本批次仅验证素材资格和回读；没有启动 Qwen/H3、没有 GPU 任务、没有生成结果。真实模型的画幅、动态质量、APP mode 与恢复能力仍须后续节点实测。
