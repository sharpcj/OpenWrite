#!/usr/bin/env python3
"""Overlay exact title/subtitle text onto a cover base image with Pillow.

WeChat covers are "image + headline": the base picture comes from an image
source without rendered text, then this module typesets the confirmed title
(and optional subtitle) pixel-exactly. Text is never left to a generative
model, so glyphs are guaranteed correct; layout defaults live in config.json
(`cover_text`) and each request may override them via its `overlay` object.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

POSITIONS = ('bottom-left', 'bottom-center', 'bottom-right',
             'top-left', 'top-center', 'top-right',
             'center-left', 'center')
MIN_TITLE_PX = 18
MIN_SUBTITLE_PX = 12
MIN_TAGLINE_PX = 12


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(os.path.abspath(__file__)), f'{name}.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image_config = _load_sibling('image_config')


def resolve_font(overlay: dict):
    from PIL import ImageFont
    explicit = overlay.get('font')
    candidates = [explicit] if explicit else []
    candidates += image_config.cover_text_defaults().get('font_candidates', [])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), 24)
            except OSError:
                continue
    raise ValueError('未找到可用中文字体；请在 config.json 的 cover_text.font_candidates '
                     '或需求 overlay.font 中配置本机字体路径（如 PingFang / Noto Sans CJK）')


def _is_cjk(char: str) -> bool:
    return '\u3400' <= char <= '\u9fff' or '\u3000' <= char <= '\u303f' or '\uff00' <= char <= '\uffef'


def _tokens(text: str) -> list:
    """CJK characters break anywhere; latin words stay together."""
    tokens, word = [], ''
    for char in text:
        if char.isspace():
            if word:
                tokens.append(word)
                word = ''
            tokens.append(' ')
        elif _is_cjk(char):
            if word:
                tokens.append(word)
                word = ''
            tokens.append(char)
        else:
            word += char
    if word:
        tokens.append(word)
    return tokens


def wrap_text(text: str, font, max_width: int) -> list:
    lines, current = [], ''
    for token in _tokens(text):
        trial = current + token
        if font.getlength(trial) <= max_width or not current.strip():
            current = trial
        else:
            lines.append(current.rstrip())
            current = token.lstrip()
    if current.strip():
        lines.append(current.rstrip())
    return lines or ['']


def _layout(overlay: dict, width: int, height: int):
    """Resolve fonts, wrapped lines and the text block box; shrink to fit.

    Three levels: big title, medium subtitle, small muted tagline.
    """
    from PIL import ImageFont
    defaults = image_config.cover_text_defaults()
    # 水平边距按宽度、垂直边距按高度，宽幅封面左侧文字也能与边缘保持留白。
    margin = max(8, int(width * float(defaults['margin_ratio'])))
    margin_y = max(8, int(height * float(defaults['margin_ratio'])))
    ratio = overlay.get('text_width_ratio')
    if ratio is not None and (type(ratio) not in (int, float) or not 0.1 <= ratio <= 0.9):
        raise ValueError('text_width_ratio 必须为 0.1–0.9 的数字')
    max_width = width - 2 * margin
    if ratio is not None:
        max_width = min(max_width, int(width * ratio))
    available = height - 2 * margin_y
    title = overlay['title']
    subtitle = overlay.get('subtitle') or ''
    tagline = overlay.get('tagline') or ''
    base = overlay.get('font_size') or max(MIN_TITLE_PX, int(height * defaults['title_height_ratio']))
    sub_base = overlay.get('subtitle_size') or max(MIN_SUBTITLE_PX, int(height * defaults['subtitle_height_ratio']))
    tag_base = overlay.get('tagline_size') or max(MIN_TAGLINE_PX, int(height * defaults['tagline_height_ratio']))
    font_path = str(resolve_font(overlay).path)
    size, sub_size, tag_size = int(base), int(sub_base), int(tag_base)
    while True:
        title_font = ImageFont.truetype(font_path, size)
        sub_font = ImageFont.truetype(font_path, sub_size) if subtitle else None
        tag_font = ImageFont.truetype(font_path, tag_size) if tagline else None
        title_lines = wrap_text(title, title_font, max_width)
        sub_lines = wrap_text(subtitle, sub_font, max_width) if subtitle else []
        tag_lines = wrap_text(tagline, tag_font, max_width) if tagline else []
        title_lh = int(size * 1.25)
        sub_lh = int(sub_size * 1.4)
        tag_lh = int(tag_size * 1.5)
        gap = int(size * 0.35) if sub_lines else 0
        gap2 = int((sub_size if sub_lines else size) * 0.6) if tag_lines else 0
        block_h = (len(title_lines) * title_lh + gap + len(sub_lines) * sub_lh
                   + gap2 + len(tag_lines) * tag_lh)
        widest = max([title_font.getlength(line) for line in title_lines]
                     + [sub_font.getlength(line) for line in sub_lines]
                     + [tag_font.getlength(line) for line in tag_lines] or [0])
        if (block_h <= available and widest <= max_width) or (
                size <= MIN_TITLE_PX and sub_size <= MIN_SUBTITLE_PX and tag_size <= MIN_TAGLINE_PX):
            if block_h > available or widest > max_width:
                raise ValueError(f'封面文案过长，缩至最小字号仍放不下（{len(title)} 字标题）；请缩短标题或副标题')
            return {'margin': margin, 'margin_y': margin_y, 'title_font': title_font, 'sub_font': sub_font,
                    'tag_font': tag_font, 'title_lines': title_lines, 'sub_lines': sub_lines,
                    'tag_lines': tag_lines, 'title_lh': title_lh, 'sub_lh': sub_lh,
                    'tag_lh': tag_lh, 'gap': gap, 'gap2': gap2, 'block_h': block_h, 'size': size}
        size = max(MIN_TITLE_PX, size - 2)
        sub_size = max(MIN_SUBTITLE_PX, sub_size - 2)
        tag_size = max(MIN_TAGLINE_PX, tag_size - 2)


def _scrim(draw_layer, width: int, height: int, box: tuple, position: str):
    """Dark gradient behind the text block so white type stays readable."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(draw_layer)
    left, top, right, bottom = box
    pad = 24
    top = max(0, top - pad)
    bottom = min(height, bottom + pad)
    if position.startswith('center'):
        draw.rectangle([max(0, left - pad), top, min(width, right + pad), bottom],
                       fill=(10, 12, 18, 120))
        return
    span = max(1, bottom - top)
    for y in range(top, bottom):
        progress = (y - top) / span
        alpha = int(165 * (progress if position.startswith('bottom') else 1 - progress))
        draw.line([(0, y), (width, y)], fill=(10, 12, 18, alpha))


def render(base, output, overlay: dict, width: int, height: int):
    """Typeset title/subtitle onto the base image; write a new PNG."""
    from PIL import Image, ImageDraw
    base, output = Path(base), Path(output)
    position = overlay.get('position') or image_config.cover_text_defaults()['position']
    if position not in POSITIONS:
        raise ValueError(f'未知封面文案位置：{position}（可用：{", ".join(POSITIONS)}）')
    color = overlay.get('color') or image_config.cover_text_defaults()['color']
    layout = _layout(overlay, width, height)
    margin = layout['margin']
    with Image.open(base) as picture:
        picture.load()
        image = picture.convert('RGBA')
    if image.size != (width, height):
        raise ValueError(f'叠字底图尺寸 {image.size} 与需求 {(width, height)} 不符')

    # 'center' 单独出现时同时表示垂直与水平居中。
    vertical, horizontal = position.split('-') if '-' in position else (position, position)
    if vertical == 'bottom':
        block_top = height - layout['margin_y'] - layout['block_h']
    elif vertical == 'top':
        block_top = layout['margin_y']
    else:
        block_top = (height - layout['block_h']) // 2

    def line_x(line, font):
        length = font.getlength(line)
        if horizontal == 'center':
            return (width - length) / 2
        if horizontal == 'right':
            return width - margin - length
        return margin

    widest = max([layout['title_font'].getlength(line) for line in layout['title_lines']]
                 + [layout['sub_font'].getlength(line) for line in layout['sub_lines']]
                 + [layout['tag_font'].getlength(line) for line in layout['tag_lines']] or [0])
    block_left = margin if horizontal == 'left' else (width - widest) / 2 if horizontal == 'center' else width - margin - widest
    use_scrim = overlay.get('scrim', image_config.cover_text_defaults()['scrim'])
    if use_scrim:
        layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
        _scrim(layer, width, height,
               (block_left, block_top, block_left + widest, block_top + layout['block_h']),
               position)
        image = Image.alpha_composite(image, layer)

    draw = ImageDraw.Draw(image)
    y = block_top
    stroke = max(1, layout['size'] // 32)
    for line in layout['title_lines']:
        x = line_x(line, layout['title_font'])
        # 偏移阴影只在深色遮罩（白字）下增加层次；浅色底深色字不加，避免重影。
        if use_scrim:
            draw.text((x + 2, y + 2), line, font=layout['title_font'], fill=(8, 10, 16, 170))
        draw.text((x, y), line, font=layout['title_font'], fill=color,
                  stroke_width=stroke, stroke_fill=color)
        y += layout['title_lh']
    if layout['sub_lines']:
        y += layout['gap']
        for line in layout['sub_lines']:
            x = line_x(line, layout['sub_font'])
            if use_scrim:
                draw.text((x + 1, y + 1), line, font=layout['sub_font'], fill=(8, 10, 16, 150))
            draw.text((x, y), line, font=layout['sub_font'], fill=color)
            y += layout['sub_lh']
    if layout['tag_lines']:
        y += layout['gap2']
        tag_color = overlay.get('tagline_color') or image_config.cover_text_defaults()['tagline_color']
        for line in layout['tag_lines']:
            x = line_x(line, layout['tag_font'])
            draw.text((x, y), line, font=layout['tag_font'], fill=tag_color)
            y += layout['tag_lh']
    image.convert('RGB').save(output, format='PNG')
    return output


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description='在封面底图上叠加标题/副标题（Pillow，文字一字不差）')
    parser.add_argument('base', help='底图 PNG（无画面文字）')
    parser.add_argument('--overlay', required=True, help='overlay 对象 JSON 文件（title 必填）')
    parser.add_argument('--output', required=True)
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--height', type=int, required=True)
    args = parser.parse_args(argv)
    overlay = json.loads(Path(args.overlay).read_text(encoding='utf-8'))
    try:
        render(args.base, args.output, overlay, args.width, args.height)
        print(json.dumps({'status': 'ready', 'output': args.output}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
