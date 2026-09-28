"""Render a tagged city-cover prompt and submit the Qwen 2.1 text-to-image graph."""

import argparse
import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "prompts/city-cover.qwen-image-2.1.json"


def get_json(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description="Generate a Qwen-Image-2.1 city cover without a reference image")
    parser.add_argument("--city", required=True, help="City or waterfront area, for example 深圳湾")
    parser.add_argument("--landmarks", required=True, help="Verified local landmarks")
    parser.add_argument("--foreground", required=True, help="Foreground elements")
    parser.add_argument("--time-of-day", default="黄昏")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:18191")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered prompt without submitting")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        parser.error("ComfyUI 必须通过本机 SSH 隧道访问")

    spec = json.loads(TEMPLATE.read_text())
    prompt = spec["promptTemplate"]
    for key, value in {"city": args.city, "landmarks": args.landmarks,
                       "foreground": args.foreground, "time_of_day": args.time_of_day}.items():
        prompt = prompt.replace("{{" + key + "}}", value.strip())
    if "{{" in prompt:
        raise ValueError("提示词模板仍有未填变量")
    print(f"模板: {spec['id']} | 标签: {', '.join(spec['tags'])}")
    print(prompt, flush=True)
    if args.dry_run:
        return
    if not args.output:
        parser.error("生成时必须指定 --output")
    if args.output.suffix.lower() != ".png":
        parser.error("ComfyUI 输出为 PNG，请将 --output 设为 .png 文件")

    graph = json.loads((ROOT / spec["workflow"]).read_text())
    graph["5"]["inputs"]["prompt"] = prompt
    graph["7"]["inputs"]["seed"] = args.seed if args.seed is not None else spec["seed"]
    request = urllib.request.Request(
        args.base_url + "/prompt",
        data=json.dumps({"prompt": graph, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        prompt_id = json.load(response)["prompt_id"]
    print(f"ComfyUI 任务: {prompt_id}", flush=True)

    for _ in range(120):
        history = get_json(args.base_url + "/history/" + prompt_id)
        if prompt_id in history:
            item = history[prompt_id]
            if item.get("status", {}).get("status_str") != "success":
                raise RuntimeError(f"生成失败: {item.get('status')}")
            for output in item.get("outputs", {}).values():
                for image in output.get("images", []):
                    query = urllib.parse.urlencode(image)
                    with urllib.request.urlopen(args.base_url + "/view?" + query, timeout=35) as response:
                        data = response.read()
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_bytes(data)
                    print(f"已保存: {args.output.resolve()}")
                    return
            raise RuntimeError("任务成功，但没有输出图片")
        time.sleep(5)
    raise TimeoutError(f"任务仍在运行，请用 ComfyUI 历史查询: {prompt_id}")


if __name__ == "__main__":
    main()
