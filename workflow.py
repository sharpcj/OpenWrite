"""Small persisted workflow for OpenWrite; local process gates, not a security boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile

import platforms
import preferences
from urllib.parse import urlparse

STEPS = ('search', 'analysis', 'draft', 'cover', 'content', 'markdown', 'format')
LABELS = ('搜索资料', '分析资料', '写正文', '生成封面', '按需生成正文配图', '生成 Markdown', '排版并保存可发布产物')
# The last two stages are completed by dedicated commands, not by `complete --step`.
SUBMITTABLE = STEPS[:-2]
# Mandatory title styles for the outline checkpoint; the third candidate defaults to 利益实用.
AGGRESSIVE_STYLE = '激进悬念'
NEUTRAL_STYLE = '客观中性'
BENEFIT_STYLE = '利益实用'
# Product limits and artifact names live in platforms.REGISTRY, not here.


def outline_required(state: dict) -> bool:
    # Legacy tasks without the field keep their original behaviour: no new gate.
    return bool(state.get('outline_approval', False))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f'缺少文件：{path.name}')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError(f'状态文件不能是符号链接：{path.name}')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.workflow-', delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} 必须是 JSON 对象')
    return value


def initialize(article: Path, title: str = '', perspective: str = 'tech',
               platform: str = platforms.WECHAT, selection_source=None,
               outline_approval: bool = True) -> dict:
    path = article / 'workflow.json'
    if path.exists():
        raise ValueError('workflow.json 已存在；继续任务请查看 status，重做请使用 reset')
    if platform not in preferences.PLATFORM_LABELS or perspective not in preferences.PERSPECTIVE_LABELS:
        raise ValueError('平台或写作视角不受支持')
    state = {'version': 1, 'title': title, 'type': perspective,
             'platform': platform, 'perspective': perspective,
             'selection_source': selection_source or {},
             'outline_approval': bool(outline_approval), 'revision': 0, 'completed': []}
    write_json(path, state)
    return state


def load(article: Path) -> dict:
    if not (article / 'workflow.json').is_file():
        raise ValueError('尚未初始化工作流；请运行 openwrite.py workflow init <文章目录>')
    state = read_json(article / 'workflow.json')
    records = state.get('completed')
    if (state.get('version') != 1 or not isinstance(records, list)
            or len(records) > len(STEPS) or type(state.get('revision')) is not int):
        raise ValueError('workflow.json 格式不正确')
    if 'outline_approval' in state and type(state['outline_approval']) is not bool:
        raise ValueError('workflow.json 的 outline_approval 必须是布尔值')
    for index, record in enumerate(records):
        if (not isinstance(record, dict) or record.get('step') != STEPS[index]
                or not isinstance(record.get('proof'), str)):
            raise ValueError('workflow.json 的已完成步骤顺序不正确')
    return state


def body(path: Path) -> str:
    text = path.read_text(encoding='utf-8').strip()
    prose = '\n'.join(line for line in text.splitlines()
                      if line.strip() and not line.lstrip().startswith(('#', '<!--')))
    if not prose.strip():
        raise ValueError(f'{path.name} 只有标题或为空，需提供实际内容')
    return text


def sources(article: Path) -> list:
    data = read_json(article / 'sources.json')
    items = data.get('sources')
    if data.get('version') != 1 or not isinstance(items, list) or not items:
        raise ValueError('sources.json 需要 version: 1 和非空 sources 列表')
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('每个来源必须是对象')
        key = item.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', key) or key in ids:
            raise ValueError('来源 id 需唯一，仅使用字母、数字、下划线或连字符')
        ids.add(key)
        if not all(isinstance(item.get(field), str) and item[field].strip()
                   for field in ('title', 'content')):
            raise ValueError('每个来源需有 title 和实际提取内容 content')
        if item.get('kind') != 'user':
            raw_url = item.get('url', '')
            if not isinstance(raw_url, str):
                raise ValueError('来源 url 必须是字符串')
            url = urlparse(raw_url)
            if url.scheme not in ('http', 'https') or not url.netloc:
                raise ValueError('网络来源需有效 URL；用户提供资料可声明 kind: user')
    return items


def outline(article: Path) -> dict:
    """Validate the user-approved title and outline that gate the draft stage."""
    for name in ('outline.json', 'outline.md'):
        if not (article / name).is_file():
            raise ValueError(f'缺少 {name}；写正文前需给出三个备选标题与大纲，并取得用户确认')
    data = read_json(article / 'outline.json')
    if data.get('version') != 1:
        raise ValueError('outline.json 需要 version: 1')
    candidates = data.get('candidates')
    if not isinstance(candidates, list) or len(candidates) < 3:
        raise ValueError('outline.json 至少需要三个备选标题')
    styles, titles = set(), []
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError('每个备选标题必须是对象')
        title, style = item.get('title'), item.get('style')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('备选标题需有非空 title')
        if not isinstance(style, str) or not style.strip():
            raise ValueError('备选标题需标注 style')
        titles.append(title.strip())
        styles.add(style.strip())
    if AGGRESSIVE_STYLE not in styles or NEUTRAL_STYLE not in styles:
        raise ValueError(f'备选标题需同时包含 {AGGRESSIVE_STYLE} 与 {NEUTRAL_STYLE} 两种风格')
    chosen = data.get('chosen_title')
    if not isinstance(chosen, str) or not chosen.strip():
        raise ValueError('outline.json 需记录用户选定的 chosen_title')
    chosen = chosen.strip()
    source = data.get('title_source')
    if source not in ('candidate', 'user'):
        raise ValueError('title_source 必须为 candidate 或 user')
    if source == 'candidate' and chosen not in titles:
        raise ValueError('选定的标题不在备选清单中；用户自定义标题请使用 title_source: user')
    if data.get('approved') is not True:
        raise ValueError('标题与大纲尚未获得用户确认（approved: true）')
    body(article / 'outline.md')
    fingerprint = file_hash(article / 'outline.md')
    if data.get('outline_hash') != fingerprint:
        raise ValueError('outline.md 在确认后发生变化，需要重新取得用户确认')
    return {'chosen_title': chosen, 'outline_hash': fingerprint}


def image_runtime():
    # Runtime import keeps backend implementation separate from the workflow controller.
    import importlib.util
    path = Path(__file__).resolve().parent / 'skills/openwrite-images/scripts/produce.py'
    spec = importlib.util.spec_from_file_location('workflow_image_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def requests(article: Path) -> list:
    data = read_json(article / 'image-requests.json')
    images = data.get('images')
    if not isinstance(images, list) or not images:
        raise ValueError('配图需求至少要有一项封面')
    runtime = image_runtime()
    # Validate the whole manifest once, including duplicate output names and identifiers.
    first = images[0].get('id') if isinstance(images[0], dict) else ''
    runtime.load_request(article, first)
    profile = platforms.for_state(load(article))
    covers = [item for item in images if item['role'] == 'cover']
    if len(covers) != 1 or covers[0]['id'] != profile['cover']['id']:
        raise ValueError(f'需求清单必须有且仅有一项 id 为 {profile["cover"]["id"]} 的封面')
    if covers[0]['output'] != profile['cover']['output']:
        raise ValueError(f'{profile["label"]}封面输出应为 {profile["cover"]["output"]}')
    rule = profile['content_images']
    content = [item for item in images if item['role'] == 'content']
    if rule['required'] and len(content) < rule['min']:
        raise ValueError(f'{profile["label"]}图文至少需要 {rule["min"]} 张正文卡片')
    if rule['max'] is not None and len(content) > rule['max']:
        raise ValueError(f'{profile["label"]}正文卡片最多 {rule["max"]} 张')
    if profile['rendered_artifact'] is None:
        orders = []
        for item in content:
            order = item.get('order')
            if type(order) is not int or order < 2:
                raise ValueError('组图正文卡片需有 order（从 2 开始的整数）；封面固定为第 1 张')
            orders.append(order)
        if len(set(orders)) != len(orders):
            raise ValueError('组图卡片的 order 不可重复')
    return images


def card_order(article: Path) -> list:
    """Upload order for a card set: cover first, then content cards by order."""
    images = requests(article)
    cover = next(item for item in images if item['role'] == 'cover')
    content = sorted((item for item in images if item['role'] == 'content'),
                     key=lambda item: item['order'])
    return [cover['output']] + [item['output'] for item in content]


def note_parts(article: Path) -> dict:
    """Split note copy into title, description and topics.

    Convention: the H1 is the title; an optional trailing `话题：a b c` line
    carries tags. Everything else is the description.
    """
    text = body(article / 'note.md')
    lines = text.splitlines()
    title = lines[0].strip()
    if not title.startswith('# '):
        raise ValueError('note.md 首行必须是 # 标题')
    title = title[2:].strip()
    topics = []
    rest = lines[1:]
    for index in range(len(rest) - 1, -1, -1):
        line = rest[index].strip()
        if not line:
            continue
        match = re.fullmatch(r'话题[:：]\s*(.+)', line)
        if match:
            topics = [tag for tag in re.split(r'[\s,，、]+', match.group(1)) if tag]
            rest = rest[:index]
        break
    desc = '\n'.join(rest).strip()
    if not desc:
        raise ValueError('note.md 需要有正文文案')
    return {'title': title, 'desc': desc, 'topics': topics}


def image_proof(article: Path, request: dict) -> dict:
    from PIL import Image
    runtime = image_runtime()
    report = read_json(article / 'image-results.json')
    if report.get('version') != 1 or not isinstance(report.get('images'), list):
        raise ValueError('image-results.json 格式不正确')
    matches = [item for item in report['images']
               if isinstance(item, dict) and item.get('id') == request['id']]
    if len(matches) != 1:
        raise ValueError(f"图片 {request['id']} 尚无唯一的执行结果")
    result = matches[0]
    expected = runtime.request_hash(request)
    if (result.get('status') != 'ready' or result.get('request_hash') != expected
            or result.get('output') != request['output']
            or (result.get('width'), result.get('height')) != (request['width'], request['height'])):
        raise ValueError(f"图片 {request['id']} 的执行结果缺失或已过期")
    path = article / request['output']
    with Image.open(path) as picture:
        picture.load()
        if picture.format != 'PNG' or picture.size != (request['width'], request['height']):
            raise ValueError(f"图片 {request['id']} 格式或尺寸不符合需求")
    return {'request': expected, 'file': file_hash(path)}


def content_decision(article: Path, images: list) -> dict:
    decision = read_json(article / 'content-images.json')
    if type(decision.get('needed')) is not bool or not isinstance(decision.get('reason'), str) or not decision['reason'].strip():
        raise ValueError('content-images.json 需明确 needed 布尔值与非空 reason')
    content = [item for item in images if item['role'] == 'content']
    if decision['needed'] != bool(content):
        raise ValueError('正文配图决策与 image-requests.json 中的正文图片清单不一致')
    return decision


def final_text(article: Path) -> str:
    text = body(article / 'draft.md')
    images = requests(article)
    content_decision(article, images)
    if platforms.for_state(load(article))['rendered_artifact'] is None:
        # 组图平台：卡片即内容本体，笔记文案不嵌图，顺序由发布清单表达。
        return text.rstrip() + '\n'
    insertions = []
    for request in images:
        if request['role'] != 'content':
            continue
        anchor = request.get('placement', '')
        matches = list(re.finditer(r'(?m)^' + re.escape(anchor) + r'$', text)) if anchor else []
        if len(matches) != 1:
            raise ValueError(f"图片 {request['id']} 的 placement 必须唯一匹配 draft.md 中的段落或标题")
        alt = request.get('alt', request['id'])
        if any(char in alt for char in ('[', ']', '\n', '\r')):
            raise ValueError('图片 alt 不能包含方括号或换行')
        index = matches[0].end()
        insertions.append((index, f"\n\n![{alt}]({request['output']})"))
    for index, addition in sorted(insertions, reverse=True):
        text = text[:index] + addition + text[index:]
    return text.rstrip() + '\n'


def proof(article: Path, step: str) -> str:
    if step == 'search':
        sources(article)
        return file_hash(article / 'sources.json')
    if step == 'analysis':
        text = body(article / 'analysis.md')
        references = re.findall(r'\bsource:([A-Za-z0-9_-]+)', text)
        ids = {item['id'] for item in sources(article)}
        if not references or not set(references).issubset(ids):
            raise ValueError('analysis.md 需用 source:<id> 关联已有来源，不能引用未知来源')
        return file_hash(article / 'analysis.md')
    if step == 'draft':
        text = body(article / 'draft.md')
        if re.search(r'!\[[^\]]*\]\(', text):
            raise ValueError('draft.md 只保存正文，不嵌入图片；图片由最终步骤整合')
        state = load(article)
        extra = {}
        if platforms.for_state(state)['rendered_artifact'] is None:
            # 卡片稿是第三步产物：改文案必须让已渲染卡片与下游一起失效。
            body(article / 'cards.md')
            extra['cards'] = file_hash(article / 'cards.md')
        if not outline_required(state):
            if not extra:
                return file_hash(article / 'draft.md')
            return digest({'draft': file_hash(article / 'draft.md'), **extra})
        plan = outline(article)
        heading = text.splitlines()[0].strip()
        if heading != f"# {plan['chosen_title']}":
            raise ValueError('draft.md 的标题必须与用户确认的标题一致；换标题请先更新 outline.md 并重新确认')
        return digest({'draft': file_hash(article / 'draft.md'),
                       'outline': plan['outline_hash'], 'title': plan['chosen_title'], **extra})
    if step == 'cover':
        cover = next(item for item in requests(article) if item['role'] == 'cover')
        return digest(image_proof(article, cover))
    if step == 'content':
        images = requests(article)
        decision = content_decision(article, images)
        images_proof = {item['id']: image_proof(article, item) for item in images if item['role'] == 'content'}
        # Validate insertion anchors before completing this stage.
        final_text(article)
        return digest({'decision': decision, 'images': images_proof})
    if step == 'markdown':
        name = platforms.for_state(load(article))['markdown_artifact']
        if (article / name).read_text(encoding='utf-8') != final_text(article):
            raise ValueError(f'{name} 与当前正文/配图不一致，请重新 finalize')
        return file_hash(article / name)
    if step == 'format':
        manifest = read_json(article / 'publish-manifest.json')
        if manifest.get('version') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('publish-manifest.json 格式不正确')
        return digest({'manifest': file_hash(article / 'publish-manifest.json'),
                       'files': publishable_files(article)})
    raise ValueError(f'未知步骤：{step}')


def publishable_files(article: Path) -> dict:
    """Fingerprints of every artifact a draft upload depends on."""
    profile = platforms.for_state(load(article))
    names = list(profile['artifacts'])
    # The cover is always part of the upload, whether it is a standalone image
    # (WeChat) or the first card of a set (Rednote).
    names.append(profile['cover']['output'])
    names.extend(item['output'] for item in requests(article) if item['role'] == 'content')
    names.extend(name for name in profile['optional_artifacts'] if (article / name).exists())
    return {name: file_hash(article / name) for name in dict.fromkeys(names)}


def stale_step(article: Path, state: dict):
    for record in state['completed']:
        try:
            if proof(article, record['step']) != record['proof']:
                return record['step'], '产物内容发生变化'
        except (OSError, ValueError) as exc:
            return record['step'], str(exc)
    return None


def checked(article: Path) -> dict:
    state = load(article)
    platforms.require_pipeline(state)
    stale = stale_step(article, state)
    if stale:
        raise ValueError(f'步骤 {stale[0]} 已失效：{stale[1]}；请 workflow reset <目录> --from {stale[0]} 后重做')
    return state


def current(state: dict):
    index = len(state['completed'])
    return STEPS[index] if index < len(STEPS) else None


def complete(article: Path, step: str, reviewed: bool = False, note: str = '') -> dict:
    state = checked(article)
    if current(state) != step:
        raise ValueError(f'当前可执行步骤为 {current(state) or "已全部完成"}，不能完成 {step}')
    if step == 'markdown':
        raise ValueError('最终 Markdown 由 workflow finalize 生成并完成')
    if step == 'format':
        raise ValueError('可发布产物由 openwrite.py format 生成并完成')
    if step == 'cover' or (step == 'content' and content_decision(article, requests(article))['needed']):
        if not reviewed or not note.strip():
            raise ValueError('图片阶段需视觉检查后提供 --reviewed 和 --note 验收记录')
    value = proof(article, step)
    if step == 'draft' and outline_required(state):
        state['title'] = outline(article)['chosen_title']
    state['completed'].append({'step': step, 'proof': value, 'note': note.strip()})
    state['revision'] += 1
    write_json(article / 'workflow.json', state)
    return state


def finalize(article: Path) -> dict:
    state = checked(article)
    if current(state) != 'markdown':
        raise ValueError('需按顺序完成前五步，才能生成最终 Markdown')
    # 第六步之后的排版由 openwrite.py format 完成。
    text = final_text(article)
    name = platforms.for_state(state)['markdown_artifact']
    output = article / name
    if output.is_symlink():
        raise ValueError(f'{name} 不能是符号链接')
    output.write_text(text, encoding='utf-8')
    state['completed'].append({'step': 'markdown', 'proof': proof(article, 'markdown'), 'note': ''})
    state['revision'] += 1
    write_json(article / 'workflow.json', state)
    return state


def reset(article: Path, step: str) -> dict:
    state = load(article)
    index = STEPS.index(step)
    if index > len(state['completed']):
        raise ValueError('不能从尚未到达的步骤退回')
    state['completed'] = state['completed'][:index]
    state['revision'] += 1
    write_json(article / 'workflow.json', state)
    return state


def require_finished(article: Path) -> dict:
    state = checked(article)
    if current(state) is not None:
        raise ValueError(f'创作尚未完成，当前步骤为 {current(state)}')
    return state


def require_image_stage(article: Path, request_id: str) -> None:
    state = checked(article)
    images = requests(article)
    matches = [item for item in images if item['id'] == request_id]
    if not matches:
        raise ValueError(f'找不到配图需求：{request_id}')
    request = matches[0]
    expected = 'cover' if request['role'] == 'cover' else 'content'
    if current(state) != expected:
        raise ValueError(f'当前步骤为 {current(state) or "已完成"}，不能执行 {expected} 图片；需要修改时先 reset')


def require_format_stage(article: Path) -> dict:
    """Formatting is the seventh stage; re-running it after completion is allowed."""
    state = checked(article)
    if current(state) not in ('format', None):
        raise ValueError(f'创作尚未完成，当前步骤为 {current(state)}；需先完成前六步再排版')
    return state


def publish_metadata(article: Path, state: dict) -> dict:
    profile = platforms.for_state(state)
    root = Path(__file__).resolve().parent
    author = preferences.credential_value(root, profile['author_key'])
    return {'title': state['title'], 'author': author, 'digest': ''}


def check_publishable(article: Path, state: dict, html_path: Path = None) -> dict:
    """Pre-upload checks so the writing stage delivers a genuinely publishable artifact."""
    from PIL import Image
    profile = platforms.for_state(state)
    limits = profile['limits']
    metadata = publish_metadata(article, state)
    title, author, digest = metadata['title'], metadata['author'], metadata['digest']
    problems = []
    if not title or not title.strip():
        problems.append('标题不能为空')
    else:
        if limits['title_chars'] and len(title) > limits['title_chars']:
            problems.append(f'标题超过 {limits["title_chars"]} 字符（当前 {len(title)}）')
        if limits['title_bytes'] and len(title.encode('utf-8')) > limits['title_bytes']:
            problems.append(f'标题超过 {limits["title_bytes"]} 字节')
    if author and limits['author_bytes'] and len(author.encode('utf-8')) > limits['author_bytes']:
        problems.append(f'作者名超过 {limits["author_bytes"]} 字节')
    if digest and limits['digest_bytes'] and len(digest.encode('utf-8')) > limits['digest_bytes']:
        problems.append(f'摘要超过 {limits["digest_bytes"]} 字节')

    cover_name = profile['cover']['output']
    cover = article / cover_name
    cover_bytes = 0
    if not cover.is_file():
        problems.append(f'缺少封面 {cover_name}')
    else:
        cover_bytes = cover.stat().st_size
        if limits['cover_bytes'] and cover_bytes > limits['cover_bytes']:
            problems.append(f'封面超过 {limits["cover_bytes"] // (1024 * 1024)}MB，{profile["label"]}素材接口会拒绝')
        try:
            with Image.open(cover) as picture:
                picture.load()
                if picture.format != 'PNG':
                    problems.append('封面必须是 PNG')
        except Exception:
            problems.append('封面无法解码')

    if profile['rendered_artifact'] is None:
        return check_card_set(article, state, title, cover_bytes, problems)

    html = html_path.read_text(encoding='utf-8') if html_path and html_path.is_file() else ''
    if not html.strip():
        problems.append('排版结果为空')
    if profile['checks']['code_blocks_converted'] and '<pre' in html.lower():
        problems.append('代码块尚未转换为微信兼容格式')
    local_images = 0
    if profile['checks']['local_images_exist']:
        for src in re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', html):
            if src.startswith(('http://', 'https://', 'data:')):
                continue
            local_images += 1
            if not (article / src).is_file():
                problems.append(f'正文图片不存在：{src}')
    if problems:
        raise ValueError('产物尚不可发布：\n  - ' + '\n  - '.join(problems))
    return {'title_chars': len(title), 'cover_bytes': cover_bytes,
            'html_chars': len(html), 'local_images': local_images}


def check_card_set(article: Path, state: dict, title: str, cover_bytes: int, problems: list) -> dict:
    """组图平台：逐张校验尺寸与顺序，并核对笔记文案。"""
    from PIL import Image
    profile = platforms.for_state(state)
    limits = profile['limits']
    try:
        parts = note_parts(article)
    except (OSError, ValueError) as exc:
        problems.append(str(exc))
        parts = {'title': '', 'desc': '', 'topics': []}
    if parts['title'] and parts['title'] != title:
        problems.append('note.md 标题与已确认标题不一致')
    if parts['desc'] and limits.get('desc_chars') and len(parts['desc']) > limits['desc_chars']:
        problems.append(f'笔记正文超过 {limits["desc_chars"]} 字（当前 {len(parts["desc"])}）')
    expected = {
        profile['cover']['output']: (profile['cover']['width'], profile['cover']['height']),
    }
    for item in requests(article):
        if item['role'] == 'content':
            expected[item['output']] = (item['width'], item['height'])
    if limits.get('max_images') and len(expected) > limits['max_images']:
        problems.append(f'组图共 {len(expected)} 张，超过单篇 {limits["max_images"]} 张上限')
    for name, size in expected.items():
        path = article / name
        if not path.is_file():
            problems.append(f'缺少卡片 {name}')
            continue
        try:
            with Image.open(path) as picture:
                picture.load()
                if picture.format != 'PNG':
                    problems.append(f'{name} 必须是 PNG')
                elif picture.size != size:
                    problems.append(f'{name} 尺寸 {picture.size} 与需求 {size} 不符')
        except Exception:
            problems.append(f'{name} 无法解码')
    if problems:
        raise ValueError('产物尚不可发布：\n  - ' + '\n  - '.join(problems))
    return {'title_chars': len(title), 'cover_bytes': cover_bytes,
            'cards': len(expected), 'desc_chars': len(parts['desc']), 'topics': len(parts['topics'])}


def build_manifest(article: Path, state: dict, theme: str, preformat: bool, checks: dict) -> dict:
    profile = platforms.for_state(state)
    manifest = {'version': 1, 'platform': preferences.task_platform(state),
                **publish_metadata(article, state),
                'theme': theme, 'preformat': bool(preformat), 'cover': profile['cover']['output'],
                'content_images': [item['output'] for item in requests(article) if item['role'] == 'content'],
                'files': publishable_files(article), 'checks': checks}
    if profile['rendered_artifact'] is None:
        parts = note_parts(article)
        manifest.update({'desc': parts['desc'], 'topics': parts['topics'], 'images': card_order(article)})
    return manifest


def complete_format(article: Path, theme: str, preformat: bool, checks: dict) -> dict:
    """Record the seventh stage; replaces the previous record when re-formatting."""
    state = load(article)
    platforms.require_pipeline(state)
    records = state['completed']
    redo = bool(records) and records[-1]['step'] == 'format'
    upstream = records[:-1] if redo else records
    if len(upstream) != len(STEPS) - 1:
        raise ValueError('需按顺序完成前六步，才能生成可发布产物')
    for record in upstream:
        try:
            actual = proof(article, record['step'])
        except (OSError, ValueError) as exc:
            raise ValueError(f'步骤 {record["step"]} 已失效：{exc}；请 workflow reset <目录> --from {record["step"]}')
        if actual != record['proof']:
            raise ValueError(f'步骤 {record["step"]} 产物已变化；请 workflow reset <目录> --from {record["step"]}')
    write_json(article / 'publish-manifest.json', build_manifest(article, state, theme, preformat, checks))
    record = {'step': 'format', 'proof': proof(article, 'format'), 'note': f'theme={theme}'}
    if redo:
        state['completed'][-1] = record
    else:
        state['completed'].append(record)
    state['revision'] += 1
    write_json(article / 'workflow.json', state)
    return state


def require_publishable(article: Path) -> dict:
    """Publishing requires the exact artifact set recorded by the seventh stage."""
    state = require_finished(article)
    manifest = read_json(article / 'publish-manifest.json')
    if manifest.get('version') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('publish-manifest.json 格式不正确，请重新 format')
    if manifest.get('title') != state['title']:
        raise ValueError('发布清单标题与工作流不一致，请重新 format')
    if manifest['files'] != publishable_files(article):
        raise ValueError('可发布产物已变化，与排版时不一致；请重新 format 后再取得用户确认发布')
    return manifest
