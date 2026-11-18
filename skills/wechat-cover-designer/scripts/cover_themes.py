#!/usr/bin/env python3
"""Data-driven cover layout themes for WeChat covers.

Mirrors the formatter's YAML-theme pattern: each preset in ``themes/`` describes
background, subject placement and text hierarchy. The resolver turns a task's
``cover_style`` snapshot into design fields (composition instructions + overlay
geometry + style/palette) that the image capability consumes. This skill owns
"how a cover looks"; openwrite-images owns fetching/rendering; writing skills
own the cover wording.
"""
from __future__ import annotations

from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[1]
THEMES_DIR = SKILL_DIR / 'themes'


def list_themes() -> list:
    return sorted(path.stem for path in THEMES_DIR.glob('*.yaml'))


def load_theme(name: str) -> dict:
    path = THEMES_DIR / f'{name}.yaml'
    if not path.is_file():
        raise ValueError(f'未知封面主题：{name}（可用：{"、".join(list_themes()) or "无"}）')
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not data.get('name'):
        raise ValueError(f'封面主题 {name} 格式不正确（需含 name）')
    return data


def find_by_layout(layout: str):
    """Match a layout description to a preset by file name or layout_aliases."""
    if not layout:
        return None
    for name in list_themes():
        theme = load_theme(name)
        aliases = theme.get('layout_aliases') or []
        if layout == name or layout in aliases:
            return theme
    return None


def _percent(ratio) -> int:
    return int(round(float(ratio) * 100))


def design_for(cover_style: dict) -> dict:
    """Resolve a cover_style snapshot into renderer-consumable design fields.

    Known layouts map to a preset and yield composition instructions + overlay
    geometry; custom layouts fall back to using the layout text as guidance.
    """
    layout = (cover_style.get('theme') or cover_style.get('layout') or '').strip()
    design = {
        'theme': None,
        'style': cover_style.get('visual_style') or None,
        'palette': [cover_style['color_tone']] if cover_style.get('color_tone') else None,
        'instructions': layout,
        'overlay_defaults': {},
        'text_defaults': {},
        'levels': None,
        'positions': None,
    }
    theme = find_by_layout(layout)
    if theme is None:
        return design
    background = theme.get('background') or {}
    subject = theme.get('subject') or {}
    text = theme.get('text') or {}
    parts = [layout]
    if background.get('rule'):
        parts.append(str(background['rule']).strip())
    if subject:
        parts.append(f"the {subject.get('region', 'right')} ~{_percent(subject.get('width_ratio', 0.5))}% "
                     f"holds {str(subject.get('scene', '')).strip()}")
        if subject.get('fit'):
            parts.append(f"the scene is a {str(subject['fit']).strip()}")
    if text:
        parts.append(f"the {text.get('region', 'left')} ~{_percent(text.get('width_ratio', 0.45))}% "
                     f"{str(text.get('guidance', '')).strip()}")
    parts.append('no text rendered in the base image')
    design['theme'] = theme.get('name')
    design['instructions'] = '; '.join(part for part in parts if part)
    design['levels'] = list(text.get('levels') or ['title'])
    design['overlay_defaults'] = {
        'position': text.get('position', 'center-left'),
        'text_width_ratio': text.get('width_ratio', 0.45),
        'scrim': text.get('scrim', False),
    }
    # 主题可声明允许的叠字方位（如居中式版式只允许水平居中相关方位）；
    # 未声明时沿用左文版式的左侧方位，保持旧主题行为。
    if text.get('positions'):
        design['positions'] = list(text['positions'])
    design['text_defaults'] = {key: text[key] for key in
                               ('title_height_ratio', 'subtitle_height_ratio',
                                'tagline_height_ratio', 'margin_ratio') if key in text}
    return design


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description='列出或解析微信封面排版主题')
    parser.add_argument('--list', action='store_true', help='列出可用主题')
    parser.add_argument('--layout', help='按版式描述解析有效设计')
    args = parser.parse_args(argv)
    if args.list:
        for name in list_themes():
            theme = load_theme(name)
            print(f'{name}\t{theme.get("name", "")}\t{theme.get("description", "")}')
        return 0
    if args.layout:
        print(json.dumps(design_for({'layout': args.layout}), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
