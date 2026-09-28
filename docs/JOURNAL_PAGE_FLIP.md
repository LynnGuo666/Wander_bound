# 旅途活页本翻页实现

调研与核对：2026-09-29。

## 为什么换掉逐帧整图

不同图像关键帧之间的纸边、装订环和阴影无法保持严格一致；直接补帧会产生重影。页面里还有可编辑文字、照片和视频，整图序列也无法让这些内容随纸面一起翻动。

## 参考实现

- [StPageFlip](https://github.com/Nodlik/StPageFlip) 把 HTML 页面作为可翻动页，支持软页、阴影、触摸和翻页事件。源码通过连续计算折线、裁切区域和阴影，而不是切换整张书图；本客户端采用其 `page-flip` 引擎。
- [React PageFlip 文档](https://nodlik.github.io/react-pageflip/) 展示了可翻动的 React 页面、翻动时间、阴影强度和上一页/下一页 API。我们直接使用同一引擎，避免另建一套静态图片播放器。
- [Turn.js](https://turnjs.com/) 也通过 HTML 页面和动态过渡实现翻书；依赖 jQuery，故这里未引入。
- 对更复杂的立体纸张，可用 [Three.js SkinnedMesh](https://threejs.org/docs/pages/SkinnedMesh.html) 给高细分纸面绑定骨骼，让顶点弯曲并映射正反面纹理。当前手账优先保留 HTML 元素的编辑能力。

## 当前方案

- 活页本、纸张纹理、装订环、相框和贴纸素材来自 Spark 上的 Qwen-Image-2.1。模型不接收用户照片。
- 翻页时复制当前活页上的 HTML 内容进入 `PageFlip`；纸面上的照片、贴纸、文字随页折叠。引擎实时绘制纸面裁切与阴影，结束后切换行程。
- 保留 30 张从千问底图渲染的连续纸页图作为素材序列和回退方案；交互端以实时翻页为主。
- 生成提示词保存在 `prompts/journal-page-turn.qwen-image-2.1.json`。静态图序列可运行 `scripts/generate-binder-turn-frames.py` 重建，生成环境需 Pillow、NumPy 和 OpenCV。
