#!/usr/bin/env python3
"""Fulfil one backend-neutral image request and return a verified local artifact."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

CAPABILITY = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CAPABILITY / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_request(article: Path, request_id: str) -> dict:
    manifest = json.loads((article / 'image-requests.json').read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or type(manifest.get('version')) is not int
            or manifest.get('version') != 1):
        raise ValueError('image-requests.json 必须使用 version: 1')
    images = manifest.get('images')
    if not isinstance(images, list) or not images:
        raise ValueError('images 必须是非空列表')
    ids, outputs = set(), set()
    selected = None
    for item in images:
        if not isinstance(item, dict):
            raise ValueError('每个图片需求必须是对象')
        name, output = item.get('id'), item.get('output')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise ValueError('图片 id 仅允许字母、数字、下划线和连字符')
        if not isinstance(output, str) or not re.fullmatch(r'[\w-]+\.png', output):
            raise ValueError('output 必须是文章同目录下的 PNG 文件名，不能包含路径')
        if name in ids or output in outputs:
            raise ValueError('图片 id 和 output 不可重复')
        ids.add(name)
        outputs.add(output)
        if item.get('role') not in ('cover', 'content'):
            raise ValueError('role 必须为 cover 或 content')
        if item['role'] == 'cover' and output != 'cover.png':
            raise ValueError('封面输出应为 cover.png')
        for key in ('width', 'height'):
            if type(item.get(key)) is not int or not 0 < item[key] <= 8192:
                raise ValueError(f'{name} 的 {key} 必须为 1–8192 的整数')
        if not isinstance(item.get('prompt'), str) or not item['prompt'].strip():
            raise ValueError(f'{name} 缺少图片内容描述 prompt')
        if 'text' in item and (not isinstance(item['text'], list)
                              or not all(isinstance(v, str) for v in item['text'])):
            raise ValueError('text 必须是画面文字的字符串列表')
        for key in ('style', 'composition', 'placement', 'alt'):
            if key in item and not isinstance(item[key], str):
                raise ValueError(f'{key} 必须是字符串')
        for key in ('palette', 'acceptance'):
            if key in item and (not isinstance(item[key], list)
                                or not all(isinstance(v, str) for v in item[key])):
                raise ValueError(f'{key} 必须是字符串列表')
        if name == request_id:
            selected = item
    if selected is None:
        raise ValueError(f'找不到图片需求：{request_id}')
    return selected


def request_hash(request: dict) -> str:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_prompt(request: dict) -> str:
    parts = [request['prompt']]
    for key in ('style', 'palette', 'composition', 'text', 'acceptance'):
        if request.get(key):
            parts.append(f'{key}: {json.dumps(request[key], ensure_ascii=False)}')
    return '\n'.join(parts)


def obtain_source(args: argparse.Namespace, request: dict, staging: Path) -> Path:
    if args.profile and args.backend != 'comfyui':
        raise ValueError('--profile 仅适用于 ComfyUI')
    if args.backend == 'file':
        if not args.source:
            raise ValueError('file 方式需要 --source，传入已有图片或宿主工具的实际输出')
        return Path(args.source).expanduser().resolve()
    if args.source:
        raise ValueError('--source 仅适用于 file 方式')
    prompt = build_prompt(request)
    if args.backend == 'comfyui':
        module = load_module('openwrite_comfy', 'comfyui_gen.py')
        # Select the model from text that must appear in the image, not Chinese design prose.
        rendered_text = ' '.join(json.dumps(text, ensure_ascii=False) for text in request.get('text', []))
        profile = module.resolve_profile(args.profile or module.DEFAULT_PROFILE, rendered_text)
        workflow = module.load_workflow(
            module.resolve_workflow_path(None, profile), prompt,
            width=request['width'], height=request['height'],
        )
        task = module.submit_prompt(workflow)
        result = module.wait_for_result(task, args.timeout)
        paths = module.extract_output_paths(result)
        if not paths:
            raise ValueError('图片后端未返回输出文件')
        return Path(paths[0]).expanduser().resolve()
    module = load_module('openwrite_api', 'generate_image.py')
    cls = module.GeminiImageGenerator if args.backend == 'gemini' else module.DALLEImageGenerator
    result = cls().generate(prompt, str(staging / 'raw.png'))
    return Path(result).resolve()


def normalize(source: Path, output: Path, request: dict, fit: str) -> None:
    from PIL import Image, ImageOps
    if not source.is_file():
        raise ValueError(f'后端返回的图片在本机不可访问：{source}')
    with Image.open(source) as original:
        original.load()
        picture = ImageOps.exif_transpose(original)
        size = (request['width'], request['height'])
        if picture.size != size:
            if fit == 'exact':
                raise ValueError(f'图片尺寸 {picture.size} 与需求 {size} 不符；可显式使用 --fit contain 或 cover')
            if fit == 'cover':
                picture = ImageOps.fit(picture, size)
            else:
                picture = ImageOps.pad(picture, size, color='white')
        if picture.mode not in ('RGB', 'RGBA'):
            picture = picture.convert('RGBA' if 'transparency' in picture.info else 'RGB')
        picture.save(output, format='PNG')


def produce(args: argparse.Namespace) -> dict:
    article = Path(args.article).expanduser().resolve()
    if not article.is_dir():
        raise ValueError(f'文章目录不存在：{article}')
    request = load_request(article, args.id)
    output = article / request['output']
    if output.is_symlink():
        raise ValueError('输出不能是符号链接')
    if output.exists() and not args.overwrite:
        raise ValueError(f'输出已存在：{output}；需要替换时显式使用 --overwrite')
    # Read the prior report before obtaining an image; malformed state must not cause paid calls.
    report_path = article / 'image-results.json'
    if report_path.is_symlink():
        raise ValueError('结果清单不能是符号链接')
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'version': 1, 'images': []}
    if (not isinstance(report, dict) or report.get('version') != 1
            or not isinstance(report.get('images'), list)
            or not all(isinstance(v, dict) for v in report['images'])):
        raise ValueError('image-results.json 格式不正确')
    # Verify decoder availability before contacting an external backend.
    import PIL.Image
    with tempfile.TemporaryDirectory(prefix='.images-', dir=article) as tmp:
        staging = Path(tmp)
        source = obtain_source(args, request, staging)
        normalized = staging / 'result.png'
        normalize(source, normalized, request, args.fit)
        result = {
            'id': request['id'], 'output': request['output'], 'backend': args.backend,
            'width': request['width'], 'height': request['height'],
            'request_hash': request_hash(request), 'status': 'ready',
            'review': 'pending', 'fit': args.fit,
        }
        report['images'] = [item for item in report['images'] if item.get('id') != args.id]
        report['images'].append(result)
        staged_report = staging / 'image-results.json'
        staged_report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        normalized.replace(output)
        staged_report.replace(report_path)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='满足一项配图需求，返回校验后的本地图片')
    parser.add_argument('article', help='含 image-requests.json 的文章目录')
    parser.add_argument('--id', required=True, help='需求清单内的图片 id')
    parser.add_argument('--backend', choices=['comfyui', 'file', 'gemini', 'dalle'], default='comfyui')
    parser.add_argument('--source', help='file 方式使用的实际图片文件，可来自宿主工具、绘图软件或用户')
    parser.add_argument('--profile', help='仅用于 ComfyUI 模型档案')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--fit', choices=['exact', 'contain', 'cover'], default='exact')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout 必须大于 0')
    try:
        print(json.dumps(produce(args), ensure_ascii=False))
        return 0
    except (Exception, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code == 0:
            return 0
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
