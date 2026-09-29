# Android 相册上传入口

`android/` 是一个只负责相册选择和上传的原生 Kotlin 应用，不包含优选、调色、裁剪、打标或视频功能。

## 使用方式

1. 用 Android Studio 打开 `android/`。
2. 运行 `app`。
3. 填写 FastAPI 地址、`MEDIA_API_TOKEN` 对应的媒体令牌和规划模块生成的 `tripId`。
4. 点击“选择照片”并提交上传。Android 13+ 使用系统 Photo Picker；旧系统使用系统文件选择器。

每张照片会转换为不超过 2560 边长、质量 86 的 JPEG，并调用现有接口：

```text
POST /api/media/photos
Authorization: Bearer <MEDIA_API_TOKEN>
Content-Type: image/jpeg
X-Trip-Id: <tripId>
X-Captured-Day: yyyy-MM-dd (可选)
```

服务端仍负责 JPEG 归一化、EXIF 清理和行程归属校验。上传后照片不会自动进入精修，必须由上游优选模块提交 selected-photos 清单。

模拟器访问本机服务时，地址通常使用 `http://10.0.2.2:4177`；真机应使用 HTTPS 或同一局域网内可达的服务地址。
