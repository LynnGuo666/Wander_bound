import sharp from 'sharp';

const MAX_INPUT_BYTES = 15 * 1024 * 1024;

export async function normalizePhoto(bytes) {
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > MAX_INPUT_BYTES) {
    throw Object.assign(new Error('图片大小需在 1 字节至 15 MiB 之间'), { status: 413 });
  }
  let image;
  try {
    image = sharp(bytes, { failOn: 'error', limitInputPixels: 50_000_000 });
    const metadata = await image.metadata();
    if (!['jpeg', 'png', 'heif', 'webp'].includes(metadata.format)) throw new Error('不支持的图片格式');
    if (metadata.width < 256 || metadata.height < 256) throw new Error('图片分辨率过低');
    const normalized = await image.rotate().resize({ width: 2560, height: 2560, fit: 'inside', withoutEnlargement: true })
      .jpeg({ quality: 88, mozjpeg: true }).toBuffer();
    const info = await sharp(normalized).metadata();
    return { bytes: normalized, width: info.width, height: info.height };
  } catch (error) {
    throw Object.assign(new Error(error.message || '无法读取图片'), { status: 415 });
  }
}

export async function analyzePhoto(bytes) {
  const stats = await sharp(bytes).stats();
  const brightness = Math.round(stats.channels.slice(0, 3).reduce((sum, channel) => sum + channel.mean, 0) / 3);
  return {
    brightness,
    exposure: brightness < 75 ? '偏暗' : brightness > 210 ? '偏亮' : '正常',
    sharpness: Number(stats.sharpness.toFixed(2)),
    entropy: Number(stats.entropy.toFixed(2)),
    processor: '本地 Sharp 图像统计',
  };
}

export async function enhancePhoto(bytes, preset) {
  if (!['natural', 'cinematic'].includes(preset)) throw Object.assign(new Error('未知修图风格'), { status: 400 });
  const image = sharp(bytes).rotate();
  if (preset === 'natural') {
    return image.normalize({ lower: 1, upper: 99 }).modulate({ saturation: 1.06 }).sharpen().jpeg({ quality: 90 }).toBuffer();
  }
  return image.normalize({ lower: 2, upper: 98 }).modulate({ saturation: 1.16, brightness: 0.99 })
    .linear(1.045, -5).sharpen().jpeg({ quality: 90 }).toBuffer();
}
