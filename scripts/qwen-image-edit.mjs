#!/usr/bin/env node
import { randomInt } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import sharp from 'sharp';
import { createQwenImageClient } from '../server/media/qwen-image.mjs';

const [, , inputPath, outputPath, prompt, seedArg] = process.argv;
if (!inputPath || !outputPath || !prompt || process.argv.length > 6) {
  console.error('用法: node --env-file=.env scripts/qwen-image-edit.mjs 输入图片.jpg 输出图片.png "中文修改指令" [seed]');
  process.exit(2);
}

const seed = seedArg === undefined ? randomInt(0x1_0000_0000) : Number(seedArg);
if (!Number.isSafeInteger(seed) || seed < 0 || seed > 0xffff_ffff) {
  console.error('seed 必须是 0 到 4294967295 的整数');
  process.exit(2);
}

const client = createQwenImageClient();
if (!client) {
  console.error('请配置 SPARK_QWEN_COMFY_URL 和 SPARK_QWEN_IMAGE_WORKFLOW_FILE');
  process.exit(2);
}

try {
  const jpeg = await sharp(await readFile(inputPath), { failOn: 'error', limitInputPixels: 50_000_000 })
    .rotate().resize({ width: 2560, height: 2560, fit: 'inside', withoutEnlargement: true })
    .jpeg({ quality: 90, mozjpeg: true }).toBuffer();
  const id = await client.queueEdit(jpeg, prompt, seed);
  console.log(`任务 ${id}，seed ${seed}。正在生成…`);
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 3_000));
    const result = await client.editStatus(id);
    if (result.status === 'running') continue;
    if (result.status === 'failed') throw new Error(`ComfyUI 任务失败：${id}`);
    const image = await client.downloadImage(result.file);
    await writeFile(outputPath, image, { flag: 'wx' });
    console.log(`已保存到 ${outputPath}`);
    process.exit(0);
  }
  throw new Error(`等待超时；任务 ID 为 ${id}，可在 ComfyUI /history/${id} 查询`);
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
