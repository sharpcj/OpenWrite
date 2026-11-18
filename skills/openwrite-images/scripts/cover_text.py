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


def validate_tech_overlay(overlay: dict):
    """Validate the opt-in renderer without reading config or loading fonts."""
    import math
    from PIL import ImageColor
    if overlay.get('position', 'center-left') not in ('center-left', 'top-left', 'bottom-left'):
        raise ValueError('tech-glow position 只支持 center-left / top-left / bottom-left')
    limits = {
        'font_size': (1, 4096), 'subtitle_size': (1, 4096), 'tagline_size': (1, 4096),
        'text_width_ratio': (0.1, 0.9), 'margin_ratio': (0, 0.45),
        'title_subtitle_gap': (0, 4096), 'subtitle_tagline_gap': (0, 4096),
        'vertical_offset': (-4096, 4096), 'glow_radius': (0, 256),
        'subtitle_glow_radius': (0, 256), 'panel_alpha': (0, 255),
        'panel_fade_ratio': (0.01, 1),
    }
    for key, (low, high) in limits.items():
        if key in overlay:
            value = overlay[key]
            if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
                raise ValueError(f'tech-glow {key} 必须为 {low}–{high} 的有限数字')
    for key in ('font', 'subtitle_font', 'tagline_font'):
        if key in overlay and (not isinstance(overlay[key], str) or not overlay[key].strip() or '\x00' in overlay[key]):
            raise ValueError(f'tech-glow {key} 必须为非空字体路径字符串')
    for key in ('color', 'subtitle_color', 'tagline_color', 'glow_color',
                'subtitle_glow_color', 'panel_color'):
        if key not in overlay:
            continue
        value = overlay[key]
        if isinstance(value, str):
            try:
                ImageColor.getcolor(value, 'RGBA')
            except (ValueError, TypeError) as exc:
                raise ValueError(f'tech-glow {key} 颜色无效') from exc
        elif not (isinstance(value, (list, tuple)) and len(value) in (3, 4)
                  and all(type(c) is int and 0 <= c <= 255 for c in value)):
            raise ValueError(f'tech-glow {key} 必须为颜色字符串或 RGB/RGBA 整数数组')


def _tech_color(value, alpha=True):
    from PIL import ImageColor
    color = ImageColor.getcolor(value, 'RGBA') if isinstance(value, str) else tuple(value)
    assert isinstance(color, tuple)  # RGBA mode always returns a tuple.
    return (color + (255,) if len(color) == 3 else color) if alpha else color[:3]


def _tech_font(overlay, key, size):
    """Separate Latin bold and CJK faces; an explicit path never falls back."""
    from PIL import ImageFont
    windows = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    if key == 'subtitle_font' and not any(_is_cjk(char) for char in overlay.get('subtitle', '')):
        candidates = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                      '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                      '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
                      '/Library/Fonts/Arial Bold.ttf',
                      '/System/Library/Fonts/Supplemental/Arial Bold.ttf', str(windows / 'arialbd.ttf')]
    else:
        weight = 'Regular' if key == 'tagline_font' else 'Bold'
        candidates = [f'/usr/share/fonts/opentype/noto/NotoSansCJK-{weight}.ttc',
                      f'/usr/share/fonts/truetype/noto/NotoSansCJK-{weight}.ttc',
                      '/System/Library/Fonts/PingFang.ttc', '/Library/Fonts/Arial Unicode.ttf',
                      str(windows / ('msyhbd.ttc' if key == 'font' else 'msyh.ttc'))]
        candidates += image_config.cover_text_defaults().get('font_candidates', [])
    if key in overlay:
        candidates = [overlay[key]]
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size)
        except (OSError, ValueError):
            continue
    if key in overlay:
        raise ValueError(f'tech-glow {key} 显式字体无效：{overlay[key]}')
    raise ValueError(f'tech-glow 未找到可用字体；请通过 overlay.{key} 配置本机字体路径')


def _tech_wrap(text, font, max_width):
    """Honor explicit newlines and split oversized Latin tokens as a last resort."""
    lines = []
    for paragraph in text.splitlines():
        for line in wrap_text(paragraph, font, max_width):
            if font.getbbox(line)[2] - font.getbbox(line)[0] <= max_width:
                lines.append(line)
                continue
            current = ''
            for char in line:
                trial = current + char
                box = font.getbbox(trial)
                if current and box[2] - box[0] > max_width:
                    lines.append(current.rstrip())
                    current = char.lstrip()
                else:
                    current = trial
            if current:
                lines.append(current)
    return [line for line in lines if line.strip()]


def _tech_layout(overlay, width, height):
    margin_ratio = overlay.get('margin_ratio', .0625)
    margin = int(width * margin_ratio)
    margin_y = int(height * margin_ratio)
    max_width = min(int(width * overlay.get('text_width_ratio', .55)), width - 2 * margin)
    available = height - 2 * margin_y
    sizes = [int(overlay.get(k, v)) for k, v in
             (('font_size', 92), ('subtitle_size', 28), ('tagline_size', 26))]
    # Caller-requested small fonts stay small rather than growing to our floors.
    floors = [min(s, f) for s, f in zip(sizes, (18, 12, 12))]
    paths = [_tech_font(overlay, k, s).path for k, s in
             zip(('font', 'subtitle_font', 'tagline_font'), sizes)]
    from PIL import ImageFont
    while True:
        rows, y = [], 0
        for level, (key, path, size) in enumerate(zip(('title', 'subtitle', 'tagline'), paths, sizes)):
            font = ImageFont.truetype(path, size)
            lines = _tech_wrap(overlay.get(key) or '', font, max_width)
            if not lines:
                continue
            if rows:
                y += int(overlay.get('subtitle_tagline_gap', 14) if level == 2
                         else overlay.get('title_subtitle_gap', 42))
            for index, line in enumerate(lines):
                bbox = font.getbbox(line)
                if index:
                    y += max(2, int(size * .2))
                rows.append({'level': level, 'text': line, 'font': font, 'bbox': bbox, 'y': y})
                y += bbox[3] - bbox[1]
        fits = y <= available and all(row['bbox'][2] - row['bbox'][0] <= max_width for row in rows)
        if fits:
            position = overlay.get('position', 'center-left')
            top = (height - y) // 2 if position == 'center-left' else (
                margin_y if position == 'top-left' else height - margin_y - y)
            top += int(overlay.get('vertical_offset', -6))
            top = max(margin_y, min(top, height - margin_y - y))
            for row in rows:
                # Place the visible ink, not the font's ascender origin.
                row['xy'] = (margin - row['bbox'][0], top + row['y'] - row['bbox'][1])
            return rows
        if sizes == floors:
            raise ValueError('封面文案过长，tech-glow 缩至最小字号仍放不下；请缩短文案')
        sizes = [max(floor, size - 2) for size, floor in zip(sizes, floors)]


def _tech_panel(image, overlay):
    from PIL import Image, ImageDraw
    layer = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(layer)
    fade_width = int(image.width * overlay.get('panel_fade_ratio', .55))
    color = _tech_color(overlay.get('panel_color', (6, 12, 38)), alpha=False)
    for x in range(fade_width):
        t = x / fade_width
        alpha = int(overlay.get('panel_alpha', 205) * (1 - t * t * (3 - 2 * t)))
        draw.line([(x, 0), (x, image.height)], fill=color + (alpha,))
    return Image.alpha_composite(image, layer)


def _tech_glow_text(base, xy, text, font, fill, glow, glow_radius):
    """Legacy tech writer's shadow → blur → blur-again → ink composites."""
    from PIL import Image, ImageDraw, ImageFilter
    shadow = Image.new('RGBA', base.size)
    ImageDraw.Draw(shadow).text((xy[0] + 3, xy[1] + 5), text, font=font, fill=(0, 0, 0, 180))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    glow1 = Image.new('RGBA', base.size)
    ImageDraw.Draw(glow1).text(xy, text, font=font, fill=glow[:3] + (255,))
    glow1 = glow1.filter(ImageFilter.GaussianBlur(glow_radius))
    glow2 = glow1.filter(ImageFilter.GaussianBlur(glow_radius // 2 or 1))
    ink = Image.new('RGBA', base.size)
    ImageDraw.Draw(ink).text(xy, text, font=font, fill=fill)
    for layer in (shadow, glow1, glow2, ink):
        base = Image.alpha_composite(base, layer)
    return base


def _render_tech(base, output, overlay, width, height):
    from PIL import Image, ImageDraw
    validate_tech_overlay(overlay)
    rows = _tech_layout(overlay, width, height)
    with Image.open(base) as picture:
        image = picture.convert('RGBA')
    if image.size != (width, height):
        raise ValueError(f'叠字底图尺寸 {image.size} 与需求 {(width, height)} 不符')
    image = _tech_panel(image, overlay)
    for row in rows:
        level, xy = row['level'], row['xy']
        if level < 2:
            image = _tech_glow_text(
                image, xy, row['text'], row['font'],
                _tech_color(overlay.get('color' if level == 0 else 'subtitle_color',
                                        (255, 255, 255, 255) if level == 0 else (140, 215, 255, 255))),
                _tech_color(overlay.get('glow_color' if level == 0 else 'subtitle_glow_color',
                                        (110, 170, 255) if level == 0 else (80, 160, 230))),
                overlay.get('glow_radius' if level == 0 else 'subtitle_glow_radius', 14 if level == 0 else 8))
        else:
            draw = ImageDraw.Draw(image)
            draw.text((xy[0] + 1, xy[1] + 2), row['text'], font=row['font'], fill=(0, 0, 0, 160))
            draw.text(xy, row['text'], font=row['font'],
                      fill=_tech_color(overlay.get('tagline_color', (210, 215, 230, 240))))
    image.convert('RGB').save(output, format='PNG')
    return Path(output)


def validate_editorial_overlay(overlay: dict):
    """Validate the warm typesetting profile before obtaining any artwork."""
    import math
    try:
        validate_tech_overlay(overlay)
    except ValueError as exc:
        raise ValueError(str(exc).replace('tech-glow', 'warm-editorial')) from exc
    if 'line_gap' in overlay:
        value = overlay['line_gap']
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 512:
            raise ValueError('warm-editorial line_gap 必须为 0–512 的有限数字')
    for key in ('title', 'subtitle', 'tagline'):
        if key in overlay and not isinstance(overlay[key], str):
            raise ValueError(f'warm-editorial {key} 必须为字符串')


def _editorial_font(overlay, key, text, size):
    # Latin headlines use real Latin bold, CJK headings use CJK bold, and
    # taglines use regular. Explicit per-level fonts always take precedence.
    if key == 'font' and not any(_is_cjk(char) for char in text):
        selection = {'subtitle': text}
        if key in overlay:
            selection['subtitle_font'] = overlay[key]
        return _tech_font(selection, 'subtitle_font', size)
    return _tech_font(overlay, key, size)


def _editorial_layout(overlay, width, height):
    from PIL import ImageFont
    validate_editorial_overlay(overlay)
    margin = int(width * overlay.get('margin_ratio', .047))
    margin_y = int(height * overlay.get('margin_ratio', .047))
    max_width = min(int(width * overlay.get('text_width_ratio', .45)), width - 2 * margin)
    sizes = [int(overlay.get(key, default)) for key, default in
             (('font_size', 62), ('subtitle_size', 44), ('tagline_size', 22))]
    floors = [min(size, floor) for size, floor in zip(sizes, (18, 12, 12))]
    texts = [overlay.get(key) or '' for key in ('title', 'subtitle', 'tagline')]
    paths = [str(_editorial_font(overlay, key, text, size).path) if text else None
             for key, text, size in zip(('font', 'subtitle_font', 'tagline_font'), texts, sizes)]
    while True:
        rows, y = [], 0
        for level, (text, path, size) in enumerate(zip(texts, paths, sizes)):
            if not text or path is None:
                continue
            font = ImageFont.truetype(path, size)
            lines = _tech_wrap(text, font, max_width)
            if rows and lines:
                y += int(overlay.get('subtitle_tagline_gap', 48) if level == 2
                         else overlay.get('title_subtitle_gap', 52))
            for index, line in enumerate(lines):
                box = font.getbbox(line)
                if index:
                    y += int(overlay.get('line_gap', 10))
                rows.append({'level': level, 'text': line, 'font': font, 'bbox': box, 'y': y})
                y += box[3] - box[1]
        if y <= height - 2 * margin_y and all(row['bbox'][2] - row['bbox'][0] <= max_width for row in rows):
            position = overlay.get('position', 'center-left')
            top = ((height - y) // 2 if position == 'center-left' else
                   margin_y if position == 'top-left' else height - margin_y - y)
            top = max(margin_y, min(top + int(overlay.get('vertical_offset', 0)), height - margin_y - y))
            for row in rows:
                row['xy'] = (margin - row['bbox'][0], top + row['y'] - row['bbox'][1])
            return rows
        if sizes == floors:
            raise ValueError('封面文案过长，warm-editorial 缩至最小字号仍放不下；请缩短文案')
        sizes = [max(floor, size - 2) for size, floor in zip(sizes, floors)]


def _render_editorial(base, output, overlay, width, height):
    """Clean warm headline + multiline message + muted tagline; no effects."""
    from PIL import Image, ImageDraw
    rows = _editorial_layout(overlay, width, height)
    with Image.open(base) as picture:
        image = picture.convert('RGBA')
    if image.size != (width, height):
        raise ValueError(f'叠字底图尺寸 {image.size} 与需求 {(width, height)} 不符')
    colors = [overlay.get('color', '#583720'), overlay.get('subtitle_color', overlay.get('color', '#583720')),
              overlay.get('tagline_color', '#928571')]
    draw = ImageDraw.Draw(image)
    for row in rows:
        draw.text(row['xy'], row['text'], font=row['font'], fill=_tech_color(colors[row['level']]))
    image.convert('RGB').save(output, format='PNG')
    return Path(output)


def render(base, output, overlay: dict, width: int, height: int):
    """Typeset title/subtitle onto the base image; write a new PNG."""
    if overlay.get('effect') == 'tech-glow':
        return _render_tech(base, output, overlay, width, height)
    if overlay.get('effect') == 'warm-editorial':
        return _render_editorial(base, output, overlay, width, height)
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
