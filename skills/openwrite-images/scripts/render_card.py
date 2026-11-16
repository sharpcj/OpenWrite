#!/usr/bin/env python3
"""Render one text-precise card from a card spec: HTML + CSS -> PNG via Playwright.

Cards are information graphics, not illustrations: the text must be exactly what
the writing side approved, so they are typeset in HTML and screenshotted at the
requested pixel size instead of being produced by an image model.

Templates and styles here are self-authored for OpenWrite (MIT).
"""
from __future__ import annotations

import html
from pathlib import Path

# Safe area defaults sit inside the verified platform ranges (side 72-96,
# top 72-112, bottom 80-120). A card spec may override them.
DEFAULT_SAFE_AREA = {'side': 84, 'top': 96, 'bottom': 104}
MIN_FONT_PX = 24
LAYOUTS = ('cover', 'bullets', 'quote')
THEMES = {
    'default': {'bg': '#f4f4f2', 'fg': '#16181d', 'accent': '#2f54eb', 'muted': '#5b616e'},
    'indigo': {'bg': '#f1f3f5', 'fg': '#0a1f3d', 'accent': '#1d39c4', 'muted': '#4a5a75'},
    'forest': {'bg': '#f5f1e8', 'fg': '#1a2e1f', 'accent': '#237804', 'muted': '#4c5c4f'},
    'kraft': {'bg': '#eedfc7', 'fg': '#2a1e13', 'accent': '#ad4e00', 'muted': '#6b5a45'},
    'midnight': {'bg': '#0e0d0c', 'fg': '#ece2cf', 'accent': '#d4a04a', 'muted': '#a89b83'},
}

VALIDATE_JS = """
() => {
  const problems = [];
  const poster = document.querySelector('.poster');
  const content = document.querySelector('.content');
  if (!poster || !content) return ['模板缺少 .poster 或 .content'];
  if (content.scrollHeight > content.clientHeight + 1) {
    problems.push('内容溢出安全区：' + content.scrollHeight + ' > ' + content.clientHeight);
  }
  if (content.scrollWidth > content.clientWidth + 1) {
    problems.push('内容横向溢出：' + content.scrollWidth + ' > ' + content.clientWidth);
  }
  const min = %d;
  for (const el of content.querySelectorAll('h1,h2,p,li,span,div')) {
    if (!el.textContent.trim()) continue;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < min) problems.push('字号低于可读下限 ' + min + 'px：' + el.textContent.trim().slice(0, 12));
  }
  const box = content.getBoundingClientRect();
  const safe = %s;
  if (box.left < safe.side - 1 || box.top < safe.top - 1 ||
      box.right > poster.clientWidth - safe.side + 1 ||
      box.bottom > poster.clientHeight - safe.bottom + 1) {
    problems.push('内容超出安全区边距');
  }
  return problems;
}
"""


def _escape(value: str) -> str:
    return html.escape(str(value), quote=True)


def build_html(card: dict, width: int, height: int) -> str:
    layout = card.get('layout', 'bullets')
    if layout not in LAYOUTS:
        raise ValueError(f'未知卡片版式：{layout}（可用：{", ".join(LAYOUTS)}）')
    theme_name = card.get('theme', 'default')
    if theme_name not in THEMES:
        raise ValueError(f'未知卡片主题：{theme_name}（可用：{", ".join(THEMES)}）')
    theme = THEMES[theme_name]
    safe = dict(DEFAULT_SAFE_AREA)
    for key, value in (card.get('safe_area') or {}).items():
        if key in safe and type(value) is int and value >= 0:
            safe[key] = value

    title = _escape(card['title'])
    subtitle = _escape(card.get('subtitle', ''))
    bullets = card.get('bullets') or []
    footer = _escape(card.get('footer', ''))
    if layout == 'cover':
        body = f'<h1>{title}</h1>'
        if subtitle:
            body += f'<p class="subtitle">{subtitle}</p>'
        if bullets:
            body += '<ul class="points">' + ''.join(f'<li>{_escape(b)}</li>' for b in bullets) + '</ul>'
    elif layout == 'quote':
        body = f'<h2>{title}</h2><blockquote>{_escape(card.get("quote", subtitle))}</blockquote>'
        if bullets:
            body += '<ul class="points">' + ''.join(f'<li>{_escape(b)}</li>' for b in bullets) + '</ul>'
    else:
        body = f'<h2>{title}</h2>'
        if subtitle:
            body += f'<p class="subtitle">{subtitle}</p>'
        if bullets:
            body += '<ul class="points">' + ''.join(f'<li>{_escape(b)}</li>' for b in bullets) + '</ul>'
        elif not subtitle:
            raise ValueError('bullets 版式需要 subtitle 或 bullets 之一，避免空白卡片')
    if footer:
        body += f'<p class="footer">{footer}</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{width}px; height:{height}px; }}
  body {{ font-family:"PingFang SC","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;
         -webkit-font-smoothing:antialiased; }}
  .poster {{ position:relative; width:{width}px; height:{height}px; background:{theme['bg']}; color:{theme['fg']};
             overflow:hidden; }}
  .content {{ position:absolute; left:{safe['side']}px; top:{safe['top']}px;
              right:{safe['side']}px; bottom:{safe['bottom']}px;
              display:flex; flex-direction:column; justify-content:center; gap:36px; overflow:hidden; }}
  h1 {{ font-size:88px; line-height:1.22; font-weight:800; letter-spacing:-1px; }}
  h2 {{ font-size:60px; line-height:1.28; font-weight:700; }}
  .subtitle {{ font-size:36px; line-height:1.6; color:{theme['muted']}; }}
  blockquote {{ font-size:44px; line-height:1.6; font-weight:600; border-left:10px solid {theme['accent']};
                padding-left:32px; }}
  ul.points {{ list-style:none; display:flex; flex-direction:column; gap:28px; }}
  ul.points li {{ font-size:38px; line-height:1.55; padding-left:40px; position:relative; }}
  ul.points li::before {{ content:""; position:absolute; left:0; top:0.55em; width:16px; height:16px;
                          background:{theme['accent']}; border-radius:4px; }}
  .footer {{ font-size:28px; color:{theme['muted']}; border-top:2px solid {theme['accent']}; padding-top:24px; }}
</style></head><body><div class="poster"><div class="content">{body}</div></div></body></html>
"""


def render(request: dict, output) -> str:
    """Render one card and validate the real DOM before accepting the result."""
    from playwright.sync_api import sync_playwright
    from PIL import Image

    output = Path(output)
    width, height = request['width'], request['height']
    card = request['card']
    markup = build_html(card, width, height)
    safe = dict(DEFAULT_SAFE_AREA)
    safe.update({k: v for k, v in (card.get('safe_area') or {}).items() if k in safe})
    script = VALIDATE_JS % (MIN_FONT_PX, repr(safe).replace("'", '"'))
    raw = output.with_suffix('.raw.png')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=2)
            page.set_content(markup, wait_until='load')
            page.evaluate('() => document.fonts.ready')
            problems = page.evaluate(script)
            if problems:
                raise ValueError('卡片版式校验未通过：\n  - ' + '\n  - '.join(problems))
            page.screenshot(path=str(raw), full_page=False)
        finally:
            browser.close()
    with Image.open(raw) as picture:
        picture.load()
        picture.convert('RGB').resize((width, height), Image.LANCZOS).save(output, format='PNG')
    raw.unlink(missing_ok=True)
    return str(output)


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description='按卡片需求渲染一张 PNG（HTML + Playwright）')
    parser.add_argument('request', help='包含单个图片需求的 JSON 文件')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    request = json.loads(Path(args.request).read_text(encoding='utf-8'))
    try:
        print(json.dumps({'status': 'ready', 'output': render(request, args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
