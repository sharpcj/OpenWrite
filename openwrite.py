#!/usr/bin/env python3
"""Project-local command entry for the OpenWrite article workspace."""
from __future__ import annotations
import layout

import argparse
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys

import workflow
import platforms
import preferences

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT / 'skills'


def _registered_skills() -> tuple:
    """Neutral capabilities plus each implemented platform's existing skills."""
    names = ['openwrite-images']
    for profile in platforms.REGISTRY.values():
        if not profile['implemented']:
            continue
        names.extend(profile['writers'].values())
        names.append(profile['renderer'])
        if profile.get('publish_implemented'):
            names.append(profile['publisher'])
    return tuple(dict.fromkeys(names))


SKILL_NAMES = _registered_skills()


def run_skill(name: str, script: str, *arguments: str) -> int:
    directory = SKILLS / name
    return subprocess.run(
        [sys.executable, str(directory / script), *arguments], cwd=directory
    ).returncode


def new_article(args: argparse.Namespace) -> int:
    if not re.fullmatch(r'[\w-]{1,100}', args.name) or args.name in {'.', '..'}:
        raise ValueError('文章目录名请使用 1–100 个汉字、字母、数字、下划线或连字符')
    title = args.title or args.name
    if '\n' in title or '\r' in title:
        raise ValueError('文章标题不能包含换行')
    selection = preferences.resolve(ROOT, getattr(args, 'platform', None),
                                    getattr(args, 'perspective', None) or getattr(args, 'type', None))
    cover = task_cover_style(args, selection['platform'])
    directory = ROOT / 'articles' / args.name
    directory.mkdir(parents=True, exist_ok=False)
    perspective = preferences.PERSPECTIVE_LABELS[selection['perspective']]
    platform_label = preferences.PLATFORM_LABELS[selection['platform']]
    checkpoint = outline_checkpoint(args)
    (layout.path(directory, 'brief.md')).write_text(
        f'# 创作需求\n\n- 主题：{title}\n- 平台：{platform_label}\n- 视角：{perspective}\n'
        f'- 标题与大纲确认：{"需要用户确认" if checkpoint else "用户已授权跳过"}\n'
        '- 受众：待根据任务补充\n- 当前阶段：工作区已创建，正文待写\n'
        '\n## 用户要求\n\n## 资料与事实依据\n\n## 配图提示词与待办\n',
        encoding='utf-8',
    )
    (layout.path(directory, 'draft.md')).write_text(f'# {title}\n', encoding='utf-8')
    (layout.path(directory, 'analysis.md')).write_text('# 资料分析\n', encoding='utf-8')
    workflow.write_json(layout.path(directory, 'sources.json'), {'version': 1, 'sources': []})
    workflow.initialize(directory, title, selection['perspective'], selection['platform'],
                        selection['selection_source'], checkpoint, cover)
    print(f'已创建文章工作区：{directory}')
    print(f'本次任务：{platform_label} / {perspective}')
    if cover:
        print('封面样式：' + json.dumps(cover, ensure_ascii=False))
    print(f'标题与大纲检查点：{"开启，写正文前需用户确认" if checkpoint else "已授权跳过"}')
    profile = platforms.spec(selection['platform'])
    if not profile['implemented']:
        print(f'{profile["label"]}选择已保存；其创作与发布能力尚未适配，暂不能推进创作流程。')
    elif not profile.get('publish_implemented'):
        print(f'{profile["label"]}选择已保存；创作流程可推进，上传适配器尚未实现，完成后需手动发布。')
    print('已创建需求、来源清单、分析与正文草稿及 workflow.json；当前步骤：search。')
    autostart_board()
    return 0


def autostart_board() -> None:
    """写作任务入口附带看板：后台拉起并开默认浏览器；OPENWRITE_BOARD_AUTO=0 可关闭。"""
    if os.environ.get('OPENWRITE_BOARD_AUTO', '1') == '0':
        return
    import board
    url, started = board.ensure_board()
    if started:
        print(f'看板已自动后台启动：{url}（已打开默认浏览器；停止：openwrite.py board --stop）')
    else:
        print(f'看板已在运行：{url}（已打开默认浏览器）')


def task_cover_style(args: argparse.Namespace, platform: str) -> dict:
    fields = ('cover_layout', 'cover_visual_style', 'cover_color_tone')
    supplied = [getattr(args, name, None) for name in fields]
    if platform != platforms.WECHAT:
        if any(value is not None for value in supplied):
            raise ValueError('WeChatCover 三个配置维度目前仅用于微信封面')
        return {}
    return preferences.cover_style(ROOT, *supplied)


def add_cover_arguments(command):
    command.add_argument('--cover-layout', help='本次微信封面版式，覆盖 WeChatCoverLayout')
    command.add_argument('--cover-visual-style', help='本次封面视觉风格，覆盖 WeChatCoverVisualStyle')
    command.add_argument('--cover-color-tone', help='本次封面色调，覆盖 WeChatCoverColorTone')


def outline_checkpoint(args: argparse.Namespace) -> bool:
    """Per-task authorization wins; otherwise use the .env feature flag."""
    if getattr(args, 'skip_outline', False):
        return False
    return preferences.outline_approval(ROOT)


def article_directory(value: str) -> Path:
    directory = Path(value).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f'文章目录不存在：{directory}')
    return directory


def render_wechat(directory: Path, state: dict, args: argparse.Namespace, staged: Path) -> int:
    """WeChat adapter: Markdown -> inline-style HTML -> WeChat code blocks."""
    profile = platforms.for_state(state)
    markdown = directory / profile['markdown_artifact']
    extra = ['--no-preformat'] if args.no_preformat else []
    result = run_skill(
        profile['renderer'], 'scripts/markdown_to_html.py',
        '--input', str(markdown), '--output', str(staged), '--theme', args.theme, *extra,
    )
    if result:
        return result
    return run_skill(profile['renderer'], 'scripts/convert-code-blocks.py', str(staged), str(staged))


# Product-layer adapters are registered per platform; the controller stays neutral.
RENDERERS = {platforms.WECHAT: render_wechat}


def format_article(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    state = workflow.require_format_stage(directory)
    profile = platforms.for_state(state)
    if profile['rendered_artifact'] is None:
        return assemble_card_set(directory, state, profile)
    render = RENDERERS.get(preferences.task_platform(state))
    if render is None:
        raise ValueError(f'{profile["label"]}排版适配器尚未实现，无法生成可发布产物')
    markdown = directory / profile['markdown_artifact']
    output = directory / profile['rendered_artifact']
    if not markdown.is_file():
        raise ValueError(f'正文文件不存在：{markdown}')
    # Preserve an existing successful artifact if conversion or any check fails.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='openwrite-format-') as tmp:
        staged = Path(tmp) / output.name
        result = render(directory, state, args, staged)
        if result:
            return result
        checks = workflow.check_publishable(directory, state, staged)
        output.write_text(staged.read_text(encoding='utf-8'), encoding='utf-8')
    workflow.complete_format(directory, args.theme, not args.no_preformat, checks)
    print(f'已完成排版并保存可发布产物：{output}')
    print(f'发布清单：{layout.existing(directory, "publish-manifest.json")}（标题：{state["title"]}；主题：{args.theme}）')
    print('七步写作已完成；上传草稿仍需用户明确确认。')
    return 0


def assemble_card_set(directory: Path, state: dict, profile: dict) -> int:
    """组图平台第七步：卡片已在第 4/5 步渲染，这里只组装、校验并写清单。"""
    checks = workflow.check_publishable(directory, state)
    requests = workflow.read_json(layout.existing(directory, 'image-requests.json'))['images']
    cover = next(item for item in requests if item['role'] == 'cover')
    theme = (cover.get('card') or {}).get('theme', 'default')
    workflow.complete_format(directory, theme, False, checks)
    manifest = workflow.read_json(layout.existing(directory, 'publish-manifest.json'))
    print(f'已组装可发布产物：{len(manifest["images"])} 张卡片 + 笔记文案（主题：{theme}）')
    print(f'发布清单：{layout.existing(directory, "publish-manifest.json")}（标题：{manifest["title"]}；'
          f'话题：{"、".join(manifest["topics"]) or "无"}）')
    if profile.get('publish_implemented'):
        print('七步写作已完成；上传仍需用户明确确认。')
    else:
        print(f'七步写作已完成；{profile["label"]}上传适配器尚未实现，请手动发布。')
    return 0


def record_publish(directory: Path, platform: str, title: str, visibility: str) -> None:
    """发布成功后的落盘记录，供看板等只读消费方判定「已发布」。"""
    workflow.write_json(layout.path(directory, 'publish-record.json'), {
        'version': 1, 'platform': platform, 'title': title, 'visibility': visibility,
        'published_at': datetime.now().astimezone().isoformat(timespec='seconds'),
    })


def publish_article(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    manifest = workflow.require_publishable(directory)
    profile = platforms.require_publish_adapter(workflow.load(directory))
    if args.title and args.title != manifest['title']:
        print(f'注意：本次标题覆盖发布清单中的「{manifest["title"]}」')
    if profile['rendered_artifact'] is None:
        return publish_card_set(args, directory, manifest, profile)
    if args.public or args.dry_run or args.headed:
        raise ValueError('--public / --dry-run / --headed 仅支持小红书图文发布')
    content = directory / profile['rendered_artifact']
    cover = directory / profile['cover']['output']
    for path in (content, cover):
        if not path.is_file():
            raise ValueError(f'发布所需文件不存在：{path}')
    title = args.title or manifest['title']
    author = args.author if args.author is not None else manifest.get('author') or None
    digest = args.digest if args.digest is not None else manifest.get('digest') or None
    arguments = ['--title', title, '--content', str(content), '--cover', str(cover)]
    if author:
        arguments.extend(['--author', author])
    if digest:
        arguments.extend(['--digest', digest])
    code = run_skill(profile['publisher'], profile['publisher_entry'], *arguments)
    if code == 0:
        record_publish(directory, workflow.load(directory)['platform'], title, 'draft')
    return code


def publish_card_set(args: argparse.Namespace, directory: Path, manifest: dict, profile: dict) -> int:
    """组图平台：按发布清单顺序上传卡片与笔记文案；默认仅自己可见。"""
    images = [directory / name for name in manifest['images']]
    for path in images:
        if not path.is_file():
            raise ValueError(f'发布所需文件不存在：{path}')
    arguments = ['--title', args.title or manifest['title'],
                 '--desc', manifest['desc'], '--images', *(str(path) for path in images),
                 '--project-root', str(ROOT), '--artifact-dir', str(directory)]
    if manifest.get('topics'):
        arguments.extend(['--topics', *manifest['topics']])
    if args.public:
        arguments.append('--public')
    if args.dry_run:
        arguments.append('--dry-run')
    if args.headed:
        arguments.append('--headed')
    code = run_skill(profile['publisher'], profile['publisher_entry'], *arguments)
    if code == 0 and not args.dry_run:
        record_publish(directory, manifest['platform'], args.title or manifest['title'],
                       'public' if args.public else 'private')
    return code


def image_article(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    workflow.require_image_stage(directory, args.id)
    arguments = [str(directory), '--id', args.id, '--backend', args.backend,
                 '--timeout', str(args.timeout)]
    if args.fit:
        arguments.extend(['--fit', args.fit])
    if args.source:
        arguments.extend(['--source', str(Path(args.source).expanduser().resolve())])
    if args.profile:
        arguments.extend(['--profile', args.profile])
    if args.overwrite:
        arguments.append('--overwrite')
    return run_skill('openwrite-images', 'scripts/produce.py', *arguments)


def workflow_command(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    if args.operation == 'init':
        selection = preferences.resolve(ROOT, args.platform, args.perspective or args.type)
        cover = task_cover_style(args, selection['platform'])
        workflow.initialize(directory, args.title or directory.name, selection['perspective'],
                            selection['platform'], selection['selection_source'],
                            outline_checkpoint(args), cover)
        autostart_board()
    elif args.operation == 'cover-style':
        state = workflow.load(directory)
        if preferences.task_platform(state) != platforms.WECHAT:
            raise ValueError('此封面样式命令目前仅用于微信任务')
        if len(state['completed']) > workflow.STEPS.index('cover'):
            raise ValueError('封面阶段已完成，请先 workflow reset <目录> --from cover')
        changes = {key: getattr(args, 'cover_' + key, None) for key in ('layout', 'visual_style', 'color_tone')}
        if not any(value is not None for value in changes.values()):
            raise ValueError('请指定至少一个 --cover-layout / --cover-visual-style / --cover-color-tone')
        updated = dict(state.get('cover_style', {}))
        updated.update({key: value for key, value in changes.items() if value is not None})
        state['cover_style'] = preferences.validate_cover_style(updated)
        state['revision'] += 1
        workflow.write_json(layout.path(directory, 'workflow.json'), state)
    elif args.operation == 'complete':
        workflow.complete(directory, args.step, args.reviewed, args.note or '')
    elif args.operation == 'reset':
        workflow.reset(directory, args.from_step)
    elif args.operation == 'finalize':
        workflow.finalize(directory)
    elif args.operation == 'migrate':
        moved = layout.migrate(directory)
        print('已迁移：' + ('、'.join(moved) if moved else '无需迁移（已是分层布局）'))
        return 0
    state = workflow.load(directory)
    platform = preferences.task_platform(state)
    perspective = preferences.task_perspective(state)
    print(f'任务平台：{preferences.PLATFORM_LABELS.get(platform, platform)}；写作视角：{preferences.PERSPECTIVE_LABELS.get(perspective, perspective)}')
    print(f'标题与大纲检查点：{"开启" if workflow.outline_required(state) else "已授权跳过"}')
    if state.get('cover_style'):
        print('封面样式：' + json.dumps(state['cover_style'], ensure_ascii=False))
    profile = platforms.for_state(state)
    if profile['implemented']:
        try:
            print(f'本阶段写作 Skill：{platforms.writer_skill(state)}')
        except ValueError as exc:
            print(f'写作 Skill：{exc}')
    else:
        print(f'写作 Skill：{profile["label"]}适配器尚未实现')
    if profile['implemented'] and not profile.get('publish_implemented'):
        print(f'{profile["label"]}上传适配器尚未实现；七步完成后需手动发布。')
    stale = workflow.stale_step(directory, state)
    done = len(state['completed'])
    for index, (step, label) in enumerate(zip(workflow.STEPS, platforms.step_labels(state))):
        marker = '已完成' if index < done else ('当前' if index == done else '待执行')
        if stale and index >= workflow.STEPS.index(stale[0]) and index < done:
            marker = '已过期'
        print(f'{index + 1}. [{marker}] {step} — {label}')
    if stale:
        print(f'检测到变更：{stale[1]}。请 workflow reset <目录> --from {stale[0]}')
    else:
        step = workflow.current(state)
        if step == 'markdown':
            print('下一步：markdown；使用 workflow finalize 生成 article.md。')
        elif step == 'format':
            print('下一步：format；使用 openwrite.py format <目录> 生成可发布产物。')
        elif step:
            hint = '写正文前需先取得用户对标题与大纲的确认（outline.md / outline.json）。' if step == 'draft' and workflow.outline_required(state) else '完成产物后使用 workflow complete。'
            print(f'下一步：{step}；{hint}')
        else:
            if profile.get('publish_implemented'):
                print('七步写作已完成，产物可发布；上传草稿仍需用户明确确认。')
            else:
                print(f'七步写作已完成，产物可发布；{profile["label"]}上传适配器尚未实现，请手动发布。')
    return 0


def board_command(args: argparse.Namespace) -> int:
    import board
    if args.stop:
        if board.stop_board(args.port):
            print(f'看板已停止（端口 {args.port}）')
        else:
            print(f'端口 {args.port} 没有可停止的看板进程')
        return 0
    board.serve(ROOT, args.port, not args.no_browser)
    return 0


def setup_command(args: argparse.Namespace) -> int:
    target, created = preferences.init_env(ROOT)
    if created:
        print(f'已创建本地配置：{target}（权限 600，已被 Git 忽略）')
    else:
        print(f'本地配置已存在，未覆盖：{target}')
    print('请编辑该文件填写 WeChatAppID、WeChatAppSecret，可选 WeChatAuthor。')
    print(f'{preferences.TEMPLATE_NAME} 只是占位模板，不要把真实密钥写入或提交。')
    return 0


def preference_command(args: argparse.Namespace) -> int:
    selection = preferences.resolve(ROOT, args.platform, args.perspective)
    if selection['platform'] == platforms.WECHAT:
        selection['cover_style'] = preferences.cover_style(ROOT)
    print(json.dumps(selection, ensure_ascii=False, indent=2))
    print(f'OutlineApproval（标题与大纲确认检查点）：{preferences.outline_approval(ROOT)}')
    profile = platforms.spec(selection['platform'])
    if not profile['implemented']:
        print(f'{profile["label"]}选择可记录；对应创作与发布能力尚未适配。', file=sys.stderr)
    elif not profile.get('publish_implemented'):
        print(f'{profile["label"]}创作能力已就绪；上传适配器尚未实现，需手动发布。', file=sys.stderr)
    return 0


def _card_runtime_status() -> str:
    """Local-only readiness of the HTML card renderer; never downloads anything."""
    if importlib.util.find_spec('playwright') is None:
        return '缺少 playwright，运行 python3 -m pip install -r requirements.txt'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            path = Path(playwright.chromium.executable_path)
        if path.exists():
            return 'OK（playwright + Chromium 就绪）'
    except Exception as exc:
        return f'检查失败：{exc}'
    return '缺少浏览器，运行 python3 -m playwright install chromium'


def doctor(args: argparse.Namespace) -> int:
    checks = [('Python >= 3.8', sys.version_info >= (3, 8))]
    checks.extend((f'依赖 {name}', importlib.util.find_spec(name) is not None)
                  for name in ('yaml', 'requests', 'PIL'))
    for name in SKILL_NAMES:
        checks.append((f'Skill {name}', (SKILLS / name / 'SKILL.md').is_file()))
    name = 'openwrite-images'
    config_path = SKILLS / name / 'config.json'
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
        profiles = config['profiles']
        if not isinstance(profiles, dict) or not profiles:
            raise ValueError('profiles 为空或格式不正确')
        for profile, settings in profiles.items():
            workflow = SKILLS / name / settings['workflow']
            json.loads(workflow.read_text(encoding='utf-8'))
            checks.append((f'{name} 模板 {profile}', True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append((f'{name} 配置/模板（{exc}）', False))
    for label, passed in checks:
        print(f'{"OK" if passed else "MISSING"}  {label}')
    print('仅检查本地环境；未连接 ComfyUI 或微信，也未读取微信凭证。')
    values = preferences.read_values(ROOT)
    comfy = values.get('COMFYUI_SERVER_URL', '').strip() or 'http://localhost:8188（默认）'
    print(f'配图来源（.env）：ComfyUI {comfy}')
    for label, keys in (('fal.ai', ('FAL_KEY', 'FAL_AI_API_KEY')),
                        ('腾讯混元 TokenHub', ('TENCENT_TOKENHUB_API_KEY',)),
                        ('Pexels', ('PEXELS_API_KEY',)),
                        ('Pixabay', ('PIXABAY_API_KEY',)),
                        ('Unsplash', ('UNSPLASH_ACCESS_KEY',))):
        configured = any(values.get(key, '').strip() for key in keys)
        print(f'  {"已配置" if configured else "未配置"}  {label}')
    planned = [profile['label'] for profile in platforms.REGISTRY.values() if not profile['implemented']]
    if planned:
        print(f'平台适配器尚未实现：{"、".join(planned)}（可选择并记录，不能推进创作流程）。')
    no_upload = [profile['label'] for profile in platforms.REGISTRY.values()
                 if profile['implemented'] and not profile.get('publish_implemented')]
    if no_upload:
        print(f'可发布产物已支持但上传适配器未实现：{"、".join(no_upload)}（需手动发布）。')
    if any(profile['implemented'] and profile['rendered_artifact'] is None
           for profile in platforms.REGISTRY.values()):
        print(f'卡片渲染：{_card_runtime_status()}')
    if not (ROOT / preferences.ENV_NAME).exists():
        print(f'提示：上传草稿前运行 python3 openwrite.py setup 生成 {preferences.ENV_NAME} 并填写微信凭证。')
    if not all(passed for _, passed in checks):
        print('缺少依赖时运行：python3 -m pip install -r requirements.txt')
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='OpenWrite 项目级文章工作区')
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='创建一篇文章的工作区，不生成正文和图片')
    new.add_argument('name', help='文章目录名，位于项目 articles/ 下')
    new.add_argument('--title', help='文章初始标题')
    new.add_argument('--platform', choices=tuple(platforms.REGISTRY), default=None)
    views = new.add_mutually_exclusive_group()
    views.add_argument('--perspective', choices=tuple(preferences.PERSPECTIVE_LABELS), default=None)
    views.add_argument('--type', choices=['tech', 'product'], default=None, help='旧版视角参数，兼容 --perspective')
    new.add_argument('--skip-outline', action='store_true', help='用户授权跳过标题与大纲确认检查点')
    add_cover_arguments(new)
    new.set_defaults(action=new_article)
    flow = commands.add_parser('workflow', help='查看、推进或退回七步创作流程')
    operations = flow.add_subparsers(dest='operation', required=True)
    for operation in ('init', 'status', 'complete', 'reset', 'finalize', 'cover-style', 'migrate'):
        command = operations.add_parser(operation)
        command.add_argument('article', help='文章目录')
        command.set_defaults(action=workflow_command)
        if operation in ('init', 'cover-style'):
            add_cover_arguments(command)
        if operation == 'init':
            command.add_argument('--title')
            command.add_argument('--platform', choices=tuple(platforms.REGISTRY), default=None)
            views = command.add_mutually_exclusive_group()
            views.add_argument('--perspective', choices=tuple(preferences.PERSPECTIVE_LABELS), default=None)
            views.add_argument('--type', choices=['tech', 'product'], default=None)
            command.add_argument('--skip-outline', action='store_true', help='用户授权跳过标题与大纲确认检查点')
        elif operation == 'complete':
            command.add_argument('--step', choices=workflow.SUBMITTABLE, required=True)
            command.add_argument('--reviewed', action='store_true', help='已实际检查图片内容')
            command.add_argument('--note', help='图片验收记录')
        elif operation == 'reset':
            command.add_argument('--from', dest='from_step', choices=workflow.STEPS, required=True)
    setup = commands.add_parser('setup', help='复制 .env.example 为本地 .env，用于填写微信凭证与流程配置')
    setup.set_defaults(action=setup_command)
    defaults = commands.add_parser('preferences', help='解析本次平台和视角，不创建任务')
    defaults.add_argument('--platform', choices=tuple(platforms.REGISTRY), default=None)
    defaults.add_argument('--perspective', choices=tuple(preferences.PERSPECTIVE_LABELS), default=None)
    defaults.set_defaults(action=preference_command)
    check = commands.add_parser('doctor', help='检查本地依赖、Skill 及模板，不联网')
    check.set_defaults(action=doctor)
    board = commands.add_parser('board', help='启动实时故事板：左侧任务列表（分页/过滤），右侧选中任务的创作看板（只读）')
    board.add_argument('--port', type=int, default=8765, help='本地端口（默认 8765，仅绑定 127.0.0.1）')
    board.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    board.add_argument('--stop', action='store_true', help='停止指定端口的后台看板进程')
    board.set_defaults(action=board_command)
    formatting = commands.add_parser('format', help='第七步：排版并保存可发布产物（渲染结果 + publish-manifest.json）')
    formatting.add_argument('article', help='文章目录路径，相对于当前工作目录')
    formatting.add_argument('--theme', default='default')
    formatting.add_argument('--no-preformat', action='store_true', help='保留原文引号与间距')
    formatting.set_defaults(action=format_article)
    image = commands.add_parser('image', help='执行独立图片能力，满足一项配图需求')
    image.add_argument('article', help='含 image-requests.json 的文章目录')
    image.add_argument('--id', required=True)
    image.add_argument('--backend',
                       choices=['auto', 'comfyui', 'file', 'html', 'gemini', 'dalle',
                                'fal', 'hunyuan', 'pexels', 'pixabay', 'unsplash'],
                       default='auto', help='auto 按配置优先级尝试多来源并自动回退')
    image.add_argument('--source', help='已有图片或宿主工具输出文件')
    image.add_argument('--profile', help='ComfyUI 模型档案')
    image.add_argument('--timeout', type=int, default=600)
    image.add_argument('--fit', choices=['exact', 'contain', 'cover'], default=None,
                       help='缺省时 auto 对图库/导入用 cover、对生图用 exact')
    image.add_argument('--overwrite', action='store_true')
    image.set_defaults(action=image_article)
    publish = commands.add_parser('publish', help='将指定文章上传到微信草稿箱（会调用微信 API）')
    publish.add_argument('article', help='文章目录路径，相对于当前工作目录')
    publish.add_argument('--title', help='默认使用 publish-manifest.json 中已确认的标题')
    publish.add_argument('--author', help='默认使用清单作者（来自 .env 的 WeChatAuthor）')
    publish.add_argument('--digest', help='默认使用清单摘要')
    publish.add_argument('--public', action='store_true',
                         help='小红书公开发布；默认仅自己可见，公开需用户明确授权')
    publish.add_argument('--dry-run', action='store_true',
                         help='小红书发布预演：仅本地校验，不登录、不上传、不发布')
    publish.add_argument('--headed', action='store_true',
                         help='小红书发布使用有头浏览器，便于观察过程或协助登录')
    publish.set_defaults(action=publish_article)
    args = parser.parse_args(argv)
    try:
        return args.action(args)
    except (OSError, ValueError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('操作已取消', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
