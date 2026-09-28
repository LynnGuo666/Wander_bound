# 照片选优的下游契约

这个文件说明选优侧（`pyserver/media` 的 L0 + VLM）的产出如何交给两个下游：**精修**（调色/裁剪）和**回忆剪辑**（③短片）。选优不另造存储格式，只把产出翻译成下游已有的契约。

## 上游产出

- `curate_trip`：给一个行程打 L0 质量分、连拍去重，得出入选的照片 id 列表（见 `quality` / `curate`）。
- `vlm.tag_image`：对一张照片出结构化 tags——场景、活动、人物、情绪、物体、时间、天气、地点线索、OCR，外加 `quality` 里的 composition/aesthetic/highlight/trash/keep。
- 落库：质量分写 `photo["quality"]`（`MediaStore.set_quality`）；tags 写 `photo["tags"]`（`set_tags`）。VLM 还没部署时，照片可能只有 quality、没有 tags，下游要能容忍这种“没打过标”。
- 原始 highest 不打分，`extract_exif` 只做无损只读解析，不重编码。

## 废片怎么判：算法、EXIF、VLM 各管一段

判“糊、歪、构图烂”不能指望任何一方单独拍板。算法只会算连续数值，看不出构图意图；VLM 能看懂画面，但它给的是相对判断，还会漏判确定性的物理错误。所以现在是三层，各自负责自己最有把握的那部分，互相作证，不互相替代。

| 层 | 负责什么 | 给出的量 |
| --- | --- | --- |
| EXIF | 相机自己记录下来的确定性事实，不用模型猜 | `orientation` / `rotated`、`focalEquiv`、`safeShutter` / `slowStops` / `shakeRisk` |
| L0 算法 | 可量化的画质事实，只给连续量不下结论 | `blur`、`spatial`、`motion`（见下） |
| VLM | 语义级的残缺：歪斜、拖影重影、主体被切被挡 | `trash` 八类 + `keep` / `highlight` |

### EXIF：物理先验

竖拍横放、方向记录与观看不一致，这是相机写死在 `Orientation` 里的，不等于 1 就是 `rotated`，比任何目测都硬。手抖同理：安全快门约为等效焦距的倒数，快门比它慢几档就是 `shakeRisk` 升档。等效焦距优先用图里的 tag，没有才按机型推画幅系数；认不出机型就留空，不填默认值——猜错画幅，安全快门整条判断跟着失效。

GPS 这里有个实测结论：M5 素材 581 张里 0 张带 GPS，是相机本身不写，不是解析 bug。所以地点要靠 VLM 的 `location_clue` 加 OCR 兜着，EXIF 这条链子是指望不上的。

### L0 算法：只给连续量

全局 Laplacian 方差是个“平均糊度”，会把该拒的整幅糊和往往是好片的浅景深糊混为一谈。`sharpness_map` 切 6×6 块分别测，看块间对比和清晰块占比，承认“分区明显”和“整体糊”是两回事。`motion_anisotropy` 量模糊的方向性，弱轴能量塌陷是拖影的特征。

这两个量都只作证据，不作结论，原因很具体：PIL 的卷积核在 uint8 上会把 Laplacian 负值截成 0，方差越小越被截断噪声主导；纯色 JPEG 有 8×8 块效应振铃，方差能到 700 以上；相机原图边缘带锐化，靠边的分块会被系统性垫高。所以阈值必须拿真样本标定，单测里用连续噪声而不是台阶式放大图，也是这个道理。

### VLM：兜语义

`trash` 列了八类，其中方向错、拖影或手抖连拍糊、构图失衡三类，本来就得靠模型看画面。同时 prompt 里写明了“不是所有不好看都算 trash”，普通随手拍靠 `keep` 给低分表达，避免动辄判删。

### 还没解决的两件事

`keep` 和 `highlight` 是相对量，一次只喂一张图给不出分布——12 张里必然只会选出三五张，逐张问模型，它只会把大多数都打成“还行”。要么改成一次喂一批、让模型内部横向比，要么在 L0 排序之后再做一轮两两比较，两条路都还没动。

歪斜检测（365 那种）也还不行。算法能测出画面的主方向，但分不清“画面歪”和“这栋楼本来就斜”；VLM 这次也漏了。要补得靠霍夫变换找长直线、再和水平参考比，这是下一步的事。

## 契约一：selected-photos（交给精修下游）

精修模块只处理已优选的照片，要一份照片 id 清单。契约是 `PUT /api/media/trips/{trip_id}/selected-photos`（整份替换、显式提交、photoIds ≤ 10000、batchId/source 各 1–128 字符、需 Bearer 令牌），语义见 `docs/photo-development.md`。

`commit_selection(media, trip_id, photo_ids, *, batch_id, source="photo-selection")` 把 curate 得出的入选 id 翻译成这份 payload，调 `MediaStore.set_selected` 落库。它是显式的一步，不并进 `curate_trip` 自动提交——精修文档要求“优选必须明确提交照片 id 清单”，而且整份替换语义下，跑到一半的 curate 不该覆盖下游已有的清单。

`set_selected` / `selected` 的存储实现在下游分支的共享 store 里（`selections/{trip}.json`）。这里只鸭子式调用，不在本分支重复实现；两条分支 PR 合并后自动接上，合并前用 FakeMedia stub 测试。

## 契约二：剪辑素材卡（留给③回忆短片，当前预留）

回忆短片已有生成链路：`jobs` 的 memories 任务拿“镜头列表”（每镜头 photoId + prompt）逐镜头用 H3 I2V 出片段、再由 ffmpeg 拼接，`GET /api/media/memories/{id}/video` 下载。缺的是上游——选哪些照片、什么顺序、每个镜头用什么信息。这正是选优加打标能补的。

`build_reel_assets(media, trip_id)` 以 selected-photos 清单为“被选”基准（和精修共用同一份，避免用到没选的照片），为每张被选照片聚合一张素材卡：

- `photoId`、`capturedDay`
- `exif`：拍摄时间 / GPS / 设备
- `quality`：L0 质量分（sharpness / exposure / flags）
- `tags`：VLM 打标（scene / activity / people / mood / objects / location_clue / ocr / highlight / keep）

卡片按 `capturedDay`（GPS）排序，对应回忆视频的时间线、动线；`highlight=true` 的单列进 `highlights`，方便挑高光镜头。剪辑模块拿这些素材卡，自己编排成 memories 的镜头列表（photoId + 由 scene/mood 生成的 I2V prompt）。选优只供原料，不重造视频生成。

### 预留说明

- ** curation/export 的 HTTP 路由暂不加**：下游分支正在大改 `photo_routes.py`，现在加路由会冲突。先用 `build_reel_assets` 纯函数加本文档占位，两条分支合并后再补只读路由；命名和路径（如 `curation/export`、`reel/plan`）待与③剪辑模块、leader 定。
- **素材卡字段可裁剪**：剪辑可能只要一部分（比如 scene/mood/highlight），按它的需要收窄，不急着塞全量。
- **“被选”基准**默认跟精修共用 selected-photos；若剪辑希望独立用 keep 集，`build_reel_assets` 可加参数切换，等③定了再放开。

## 和既有接口的分工

| 下游 | 要什么 | 由谁提供 |
| --- | --- | --- |
| 精修 develop | 照片 id 清单 | `commit_selection` → `PUT selected-photos` |
| 回忆剪辑 memories | 被选照片的提取信息 | `build_reel_assets` 素材卡 |
| 视频生成 jobs.memories | 镜头列表（photoId + prompt） | 剪辑模块编排，不在选优范围 |
