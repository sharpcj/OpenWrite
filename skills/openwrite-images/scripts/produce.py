#!/usr/bin/env python3
"""Fulfil one backend-neutral image request and return a verified local artifact.

Sources: local ComfyUI, online generation (fal.ai / Tencent Hunyuan), free
stock libraries (Pexels / Pixabay / Unsplash), existing local files (host
tool output, user art, official-doc illustrations downloaded by the agent)
and HTML card rendering. `--backend auto` walks the configured priority
order and falls back on failure; the request may pin its own order via
`preferred_sources`. Addresses and keys live in openwrite.yaml (image_sources).
"""
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
PROJECT_ROOT = CAPABILITY.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import layout


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CAPABILITY / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image_config = load_module('openwrite_image_config', 'image_config.py')


def _cover_styles():
    """Load the cover-designer skill's style resolver (design presets live there)."""
    path = PROJECT_ROOT / 'skills/wechat-cover-designer/scripts/cover_styles.py'
    spec = importlib.util.spec_from_file_location('openwrite_cover_styles', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

OVERLAY_POSITIONS = ('bottom-left', 'bottom-center', 'bottom-right',
                     'top-left', 'top-center', 'top-right',
                     'center-left', 'center')


def _validate_overlay(item: dict) -> None:
    overlay = item['overlay']
    if not isinstance(overlay, dict):
        raise ValueError('overlay 必须是对象，描述封面标题/副标题叠字')
    if item.get('role') != 'cover':
        raise ValueError('overlay 叠字仅用于封面（role: cover）')
    if 'card' in item:
        raise ValueError('overlay 与 card 不能同时使用；卡片文字由 html 后端排版')
    if not isinstance(overlay.get('title'), str) or not overlay['title'].strip():
        raise ValueError('overlay 需有非空 title（封面大标题，可短于文章标题）')
    if item.get('text'):
        raise ValueError('配置 overlay 叠字时底图不应再渲染画面文字；请把 text 置空，避免文字重复')
    for key in ('subtitle', 'tagline', 'color', 'tagline_color', 'font'):
        if key in overlay and not isinstance(overlay[key], str):
            raise ValueError(f'overlay.{key} 必须是字符串')
    if 'position' in overlay and overlay['position'] not in OVERLAY_POSITIONS:
        raise ValueError(f'overlay.position 只能为 {", ".join(OVERLAY_POSITIONS)}')
    for key in ('font_size', 'subtitle_size', 'tagline_size'):
        if key in overlay and (type(overlay[key]) is not int or not 8 <= overlay[key] <= 512):
            raise ValueError(f'overlay.{key} 必须为 8–512 的整数')
    if 'text_width_ratio' in overlay and (type(overlay['text_width_ratio']) not in (int, float)
                                            or not 0.1 <= overlay['text_width_ratio'] <= 0.9):
        raise ValueError('overlay.text_width_ratio 必须为 0.1–0.9 的数字')
    if 'scrim' in overlay and type(overlay['scrim']) is not bool:
        raise ValueError('overlay.scrim 必须是布尔值')
    if overlay.get('effect', 'plain') not in ('plain', 'tech-glow', 'warm-editorial'):
        raise ValueError('overlay.effect 只能为 plain / tech-glow / warm-editorial')
    if overlay.get('effect') in ('tech-glow', 'warm-editorial'):
        renderer = load_module('openwrite_cover_validation', 'cover_text.py')
        # Resolve actual fonts and fit before any potentially billable backend.
        if overlay['effect'] == 'tech-glow':
            renderer.validate_tech_overlay(overlay)
            renderer._tech_layout(overlay, item['width'], item['height'])
        else:
            renderer._editorial_layout(overlay, item['width'], item['height'])


def _cover_requirement(article: Path, request: dict) -> dict:
    """Use task snapshots, never mutable config defaults, to resolve cover design."""
    state_file = layout.existing(article, 'workflow.json')
    if request.get('role') != 'cover' or not state_file.is_file():
        return request
    state = json.loads(state_file.read_text(encoding='utf-8'))
    if state.get('platform', 'wechat') != 'wechat' or not state.get('cover_style'):
        return request
    style = state['cover_style']
    if (not isinstance(style, dict) or set(style) - {'style', 'layout', 'visual_style', 'color_tone'}
            or not all(isinstance(v, str) and v.strip() for v in style.values())):
        raise ValueError('任务 cover_style 格式不正确')
    import copy
    result = copy.deepcopy(request)
    result['cover_style'] = dict(style)
    design = _cover_styles().design_for(style)
    if design.get('visual_style'):
        result['style'] = design['visual_style']
    if design.get('palette'):
        result['palette'] = design['palette']
    if design.get('style') is not None:
        # 预设版式：底图不渲染文字，叠字几何由样式约束。
        if result.get('text'):
            raise ValueError('预设封面版式采用后期叠字，请将 text 置空并提供 overlay 标题')
        defaults = design['overlay_defaults']
        overlay = result.setdefault('overlay', {'title': state.get('title', '')})
        positions = design.get('positions') or ('top-left', 'center-left', 'bottom-left')
        if overlay.get('position') not in positions:
            overlay['position'] = defaults.get('position', 'center-left')
        cap = defaults.get('text_width_ratio', 0.45)
        overlay['text_width_ratio'] = min(overlay.get('text_width_ratio', cap), cap)
        # Declared defaults enter the effective request and fingerprint. Editing
        # a preset intentionally invalidates prior results that used that preset.
        for key, value in defaults.items():
            if key not in ('position', 'text_width_ratio', 'scrim'):
                overlay.setdefault(key, value)
        overlay.setdefault('scrim', defaults.get('scrim', False))
        # 文字层次由样式定义：未声明的层次不渲染（如仅大标题的样式）。
        levels = design.get('levels') or ['title']
        for level in ('subtitle', 'tagline'):
            if level not in levels:
                overlay.pop(level, None)
    if design.get('instructions'):
        result['composition'] = '\n'.join(
            v for v in (result.get('composition', ''), design['instructions']) if v)
    if result.get('overlay'):
        _validate_overlay(result)
    return result


def load_request(article: Path, request_id: str) -> dict:
    manifest = json.loads((layout.existing(article, 'image-requests.json')).read_text(encoding='utf-8'))
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
        # 封面文件名由平台注册表约定，控制器校验；本能力保持平台中立。
        if 'order' in item and (type(item['order']) is not int or item['order'] < 1):
            raise ValueError('order 必须是从 1 开始的整数')
        if 'card' in item:
            card = item['card']
            if not isinstance(card, dict):
                raise ValueError('card 必须是对象，描述卡片版式与内容')
            if not isinstance(card.get('title'), str) or not card['title'].strip():
                raise ValueError('card 需有非空 title')
            for key in ('layout', 'theme', 'subtitle', 'footer'):
                if key in card and not isinstance(card[key], str):
                    raise ValueError(f'card.{key} 必须是字符串')
            if 'bullets' in card and (not isinstance(card['bullets'], list)
                                      or not all(isinstance(v, str) for v in card['bullets'])):
                raise ValueError('card.bullets 必须是字符串列表')
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
        if 'preferred_sources' in item:
            sources = item['preferred_sources']
            if (not isinstance(sources, list) or not sources
                    or not all(isinstance(v, str) and v in image_config.BACKENDS for v in sources)
                    or len(set(sources)) != len(sources)):
                raise ValueError(f'preferred_sources 必须是不重复的后端列表（可选：{", ".join(image_config.BACKENDS)}）')
        if 'source_file' in item and not isinstance(item['source_file'], str):
            raise ValueError('source_file 必须是已有图片的文件路径字符串')
        if 'source_url' in item and not isinstance(item['source_url'], str):
            raise ValueError('source_url 必须是字符串，记录图片原始出处（如官方文档插图链接）')
        if 'attribution' in item and not isinstance(item['attribution'], str):
            raise ValueError('attribution 必须是字符串，记录版权/署名信息')
        if 'keywords' in item and (not isinstance(item['keywords'], list)
                                   or not item['keywords']
                                   or not all(isinstance(v, str) and v.strip() for v in item['keywords'])):
            raise ValueError('keywords 必须是非空字符串列表，供图库搜索使用')
        if 'overlay' in item:
            _validate_overlay(item)
        if name == request_id:
            selected = item
    if selected is None:
        raise ValueError(f'找不到图片需求：{request_id}')
    return _cover_requirement(article, selected)


def request_hash(request: dict) -> str:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_prompt(request: dict) -> str:
    parts = [request['prompt']]
    for key in ('style', 'palette', 'composition', 'text', 'acceptance'):
        if request.get(key):
            parts.append(f'{key}: {json.dumps(request[key], ensure_ascii=False)}')
    return '\n'.join(parts)


def _file_source(args: argparse.Namespace, request: dict) -> Path:
    source = args.source or request.get('source_file')
    if not source:
        raise ValueError('file 方式需要 --source 或需求中的 source_file（已有图片、宿主工具输出或官方文档插图）')
    return Path(source).expanduser().resolve()


def obtain_backend(backend: str, args: argparse.Namespace, request: dict, staging: Path):
    """Run one backend; return (local file, provenance metadata)."""
    if backend == 'file':
        meta = {}
        if request.get('source_url'):
            meta['source_url'] = request['source_url']
        if request.get('attribution'):
            meta['attribution'] = request['attribution']
        return _file_source(args, request), meta
    if args.source and backend != 'file':
        raise ValueError('--source 仅适用于 file 方式')
    if backend == 'html':
        if not isinstance(request.get('card'), dict):
            raise ValueError('html 方式需要 card 字段，描述卡片版式与内容')
        module = load_module('openwrite_card', 'render_card.py')
        return Path(module.render(request, staging / 'card.png')).resolve(), {}
    prompt = build_prompt(request)
    if backend == 'comfyui':
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
        return Path(paths[0]).expanduser().resolve(), {'model': profile}
    if backend in image_config.ONLINE_BACKENDS:
        module = load_module('openwrite_online', 'image_sources.py')
        raw = staging / 'raw.png'
        meta = module.generate_online(backend, prompt, raw,
                                      request['width'], request['height'], args.timeout)
        return raw.resolve(), meta
    if backend in image_config.STOCK_BACKENDS:
        if not request.get('keywords'):
            raise ValueError(f'{backend} 图库搜索需要需求中的 keywords 字段')
        module = load_module('openwrite_online', 'image_sources.py')
        raw = staging / 'raw.png'
        meta = module.fetch_stock(backend, request['keywords'], raw,
                                  request['width'], request['height'], args.timeout)
        return raw.resolve(), meta
    if backend in ('gemini', 'dalle'):
        module = load_module('openwrite_api', 'generate_image.py')
        cls = module.GeminiImageGenerator if backend == 'gemini' else module.DALLEImageGenerator
        result = cls().generate(prompt, str(staging / 'raw.png'))
        return Path(result).resolve(), {}
    raise ValueError(f'未知图片来源：{backend}')


def obtain_source(args: argparse.Namespace, request: dict, staging: Path):
    """Explicit-backend entry kept for compatibility; returns (path, meta)."""
    if args.profile and args.backend != 'comfyui':
        raise ValueError('--profile 仅适用于 ComfyUI')
    return obtain_backend(args.backend, args, request, staging)


def backend_available(backend: str, args: argparse.Namespace, request: dict) -> bool:
    """Whether auto mode may attempt this backend without guaranteed failure."""
    if backend == 'file':
        return bool(args.source or request.get('source_file'))
    if backend == 'html':
        return isinstance(request.get('card'), dict)
    if backend == 'comfyui':
        return True
    return bool(image_config.backend_key(backend))


def default_fit(backend: str) -> str:
    """Auto mode: generators hit the exact size; photos/imports are cropped."""
    return 'cover' if backend in image_config.STOCK_BACKENDS + ('file',) else 'exact'


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


def apply_overlay(normalized: Path, request: dict, staging: Path) -> Path:
    """WeChat cover = base image + Pillow-typeset title/subtitle."""
    module = load_module('openwrite_cover_text', 'cover_text.py')
    output = staging / 'overlay.png'
    module.render(normalized, output, request['overlay'], request['width'], request['height'])
    return output


def produce(args: argparse.Namespace) -> dict:
    article = Path(args.article).expanduser().resolve()
    if not article.is_dir():
        raise ValueError(f'文章目录不存在：{article}')
    request = load_request(article, args.id)
    if args.profile and args.backend not in ('comfyui', 'auto'):
        raise ValueError('--profile 仅适用于 ComfyUI')
    output = article / request['output']
    if output.is_symlink():
        raise ValueError('输出不能是符号链接')
    if output.exists() and not args.overwrite:
        raise ValueError(f'输出已存在：{output}；需要替换时显式使用 --overwrite')
    # Read the prior report before obtaining an image; malformed state must not cause paid calls.
    report_path = layout.path(article, 'image-results.json')
    if report_path.is_symlink():
        raise ValueError('结果清单不能是符号链接')
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'version': 1, 'images': []}
    if (not isinstance(report, dict) or report.get('version') != 1
            or not isinstance(report.get('images'), list)
            or not all(isinstance(v, dict) for v in report['images'])):
        raise ValueError('image-results.json 格式不正确')
    if args.backend == 'auto':
        order = request.get('preferred_sources') or image_config.source_priority(request['role'])
        candidates = [name for name in order if backend_available(name, args, request)]
        skipped = [name for name in order if name not in candidates]
        if not candidates:
            raise ValueError('没有可用的图片来源：'
                             + ('、'.join(skipped) + ' 均未配置或无输入文件；' if skipped else '')
                             + '请在 openwrite.yaml 的 image_sources 配置 comfyui_server_url / fal_key / tencent_tokenhub_api_key / 图库密钥，'
                               '或用 --backend file --source 导入已有图片')
    else:
        candidates = [args.backend]
    # Verify decoder availability before contacting an external backend.
    import PIL.Image
    with tempfile.TemporaryDirectory(prefix='.images-', dir=article) as tmp:
        staging = Path(tmp)
        attempts, source, meta, used, fit = [], None, {}, None, None
        for backend in candidates:
            fit = args.fit or (default_fit(backend) if args.backend == 'auto' else 'exact')
            try:
                source, meta = obtain_backend(backend, args, request, staging)
                normalized = staging / 'result.png'
                normalize(source, normalized, request, fit)
                used = backend
                break
            except (Exception, SystemExit) as exc:
                if isinstance(exc, SystemExit) and exc.code == 0:
                    raise
                if args.backend != 'auto':
                    raise
                message = (f'执行中断（exit {exc.code}），详见 stderr 日志'
                           if isinstance(exc, SystemExit) else str(exc))
                attempts.append({'backend': backend, 'error': message})
                print(f'[WARN] 来源 {backend} 失败，回退下一来源：{message}', file=sys.stderr)
        if used is None:
            detail = '\n  - '.join(f'{item["backend"]}: {item["error"]}' for item in attempts)
            raise ValueError(f'所有图片来源均失败：\n  - {detail}')
        if request.get('overlay'):
            normalized = apply_overlay(normalized, request, staging)
        result = {
            'id': request['id'], 'output': request['output'], 'backend': used,
            'width': request['width'], 'height': request['height'],
            'request_hash': request_hash(request), 'status': 'ready',
            'review': 'pending', 'fit': fit,
        }
        for key in ('source_url', 'attribution', 'model', 'query'):
            if meta.get(key):
                result[key] = meta[key]
        if attempts:
            result['attempts'] = attempts
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
    parser.add_argument('--backend', choices=['auto', *image_config.BACKENDS], default='auto',
                        help='auto 按优先级依次尝试并自动回退；也可显式指定单一来源')
    parser.add_argument('--source', help='file 方式使用的实际图片文件，可来自宿主工具、绘图软件或用户')
    parser.add_argument('--profile', help='仅用于 ComfyUI 模型档案')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--fit', choices=['exact', 'contain', 'cover'], default=None,
                        help='缺省时 auto 对图库/导入用 cover、对生图用 exact；显式后端用 exact')
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
