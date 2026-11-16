#!/usr/bin/env python3
"""Project-local command entry for the OpenWrite article workspace."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import workflow
import platforms
import preferences

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT / 'skills'
# Neutral capabilities plus every implemented platform's skills, derived from the registry.
SKILL_NAMES = tuple(dict.fromkeys(
    ['openwrite-images'] + [
        skill
        for profile in platforms.REGISTRY.values() if profile['implemented']
        for skill in [*profile['writers'].values(), profile['renderer'], profile['publisher']]
    ]
))


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
    directory = ROOT / 'articles' / args.name
    directory.mkdir(parents=True, exist_ok=False)
    perspective = preferences.PERSPECTIVE_LABELS[selection['perspective']]
    platform_label = preferences.PLATFORM_LABELS[selection['platform']]
    checkpoint = outline_checkpoint(args)
    (directory / 'brief.md').write_text(
        f'# 创作需求\n\n- 主题：{title}\n- 平台：{platform_label}\n- 视角：{perspective}\n'
        f'- 标题与大纲确认：{"需要用户确认" if checkpoint else "用户已授权跳过"}\n'
        '- 受众：待根据任务补充\n- 当前阶段：工作区已创建，正文待写\n'
        '\n## 用户要求\n\n## 资料与事实依据\n\n## 配图提示词与待办\n',
        encoding='utf-8',
    )
    (directory / 'draft.md').write_text(f'# {title}\n', encoding='utf-8')
    (directory / 'analysis.md').write_text('# 资料分析\n', encoding='utf-8')
    workflow.write_json(directory / 'sources.json', {'version': 1, 'sources': []})
    workflow.initialize(directory, title, selection['perspective'], selection['platform'],
                        selection['selection_source'], checkpoint)
    print(f'已创建文章工作区：{directory}')
    print(f'本次任务：{platform_label} / {perspective}')
    print(f'标题与大纲检查点：{"开启，写正文前需用户确认" if checkpoint else "已授权跳过"}')
    if selection['platform'] == 'rednote':
        print('小红书选择已保存；其创作与发布能力尚未适配，暂不能推进微信流程。')
    print('已创建需求、来源清单、分析与正文草稿及 workflow.json；当前步骤：search。')
    return 0


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
    render = RENDERERS.get(preferences.task_platform(state))
    if render is None or not profile['rendered_artifact']:
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
    print(f'发布清单：{directory / "publish-manifest.json"}（标题：{state["title"]}；主题：{args.theme}）')
    print('七步写作已完成；上传草稿仍需用户明确确认。')
    return 0


def publish_article(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    manifest = workflow.require_publishable(directory)
    profile = platforms.for_state(workflow.load(directory))
    content = directory / profile['rendered_artifact']
    cover = directory / profile['cover']['output']
    for path in (content, cover):
        if not path.is_file():
            raise ValueError(f'发布所需文件不存在：{path}')
    title = args.title or manifest['title']
    author = args.author if args.author is not None else manifest.get('author') or None
    digest = args.digest if args.digest is not None else manifest.get('digest') or None
    if args.title and args.title != manifest['title']:
        print(f'注意：本次标题覆盖发布清单中的「{manifest["title"]}」')
    arguments = ['--title', title, '--content', str(content), '--cover', str(cover)]
    if author:
        arguments.extend(['--author', author])
    if digest:
        arguments.extend(['--digest', digest])
    return run_skill(profile['publisher'], profile['publisher_entry'], *arguments)


def image_article(args: argparse.Namespace) -> int:
    directory = article_directory(args.article)
    workflow.require_image_stage(directory, args.id)
    arguments = [str(directory), '--id', args.id, '--backend', args.backend,
                 '--fit', args.fit, '--timeout', str(args.timeout)]
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
        workflow.initialize(directory, args.title or directory.name, selection['perspective'],
                            selection['platform'], selection['selection_source'],
                            outline_checkpoint(args))
    elif args.operation == 'complete':
        workflow.complete(directory, args.step, args.reviewed, args.note or '')
    elif args.operation == 'reset':
        workflow.reset(directory, args.from_step)
    elif args.operation == 'finalize':
        workflow.finalize(directory)
    state = workflow.load(directory)
    platform = preferences.task_platform(state)
    perspective = preferences.task_perspective(state)
    print(f'任务平台：{preferences.PLATFORM_LABELS.get(platform, platform)}；写作视角：{preferences.PERSPECTIVE_LABELS.get(perspective, perspective)}')
    print(f'标题与大纲检查点：{"开启" if workflow.outline_required(state) else "已授权跳过"}')
    profile = platforms.for_state(state)
    if profile['implemented']:
        try:
            print(f'本阶段写作 Skill：{platforms.writer_skill(state)}')
        except ValueError as exc:
            print(f'写作 Skill：{exc}')
    else:
        print(f'写作 Skill：{profile["label"]}适配器尚未实现')
    if platform == 'rednote':
        print('小红书任务选择已保存；对应创作与发布适配尚未实现。')
    stale = workflow.stale_step(directory, state)
    done = len(state['completed'])
    for index, (step, label) in enumerate(zip(workflow.STEPS, workflow.LABELS)):
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
            print('七步写作已完成，产物可发布；上传草稿仍需用户明确确认。')
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
    print(json.dumps(selection, ensure_ascii=False, indent=2))
    print(f'OutlineApproval（标题与大纲确认检查点）：{preferences.outline_approval(ROOT)}')
    if selection['platform'] == 'rednote':
        print('小红书选择可记录；对应创作与发布能力尚未适配。', file=sys.stderr)
    return 0


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
    planned = [profile['label'] for profile in platforms.REGISTRY.values() if not profile['implemented']]
    if planned:
        print(f'平台适配器尚未实现：{"、".join(planned)}（可选择并记录，不能推进创作流程）。')
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
    new.set_defaults(action=new_article)
    flow = commands.add_parser('workflow', help='查看、推进或退回七步创作流程')
    operations = flow.add_subparsers(dest='operation', required=True)
    for operation in ('init', 'status', 'complete', 'reset', 'finalize'):
        command = operations.add_parser(operation)
        command.add_argument('article', help='文章目录')
        command.set_defaults(action=workflow_command)
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
    formatting = commands.add_parser('format', help='第七步：排版并保存可发布产物（渲染结果 + publish-manifest.json）')
    formatting.add_argument('article', help='文章目录路径，相对于当前工作目录')
    formatting.add_argument('--theme', default='default')
    formatting.add_argument('--no-preformat', action='store_true', help='保留原文引号与间距')
    formatting.set_defaults(action=format_article)
    image = commands.add_parser('image', help='执行独立图片能力，满足一项配图需求')
    image.add_argument('article', help='含 image-requests.json 的文章目录')
    image.add_argument('--id', required=True)
    image.add_argument('--backend', choices=['comfyui', 'file', 'gemini', 'dalle'], default='comfyui')
    image.add_argument('--source', help='已有图片或宿主工具输出文件')
    image.add_argument('--profile', help='ComfyUI 模型档案')
    image.add_argument('--timeout', type=int, default=600)
    image.add_argument('--fit', choices=['exact', 'contain', 'cover'], default='exact')
    image.add_argument('--overwrite', action='store_true')
    image.set_defaults(action=image_article)
    publish = commands.add_parser('publish', help='将指定文章上传到微信草稿箱（会调用微信 API）')
    publish.add_argument('article', help='文章目录路径，相对于当前工作目录')
    publish.add_argument('--title', help='默认使用 publish-manifest.json 中已确认的标题')
    publish.add_argument('--author', help='默认使用清单作者（来自 .env 的 WeChatAuthor）')
    publish.add_argument('--digest', help='默认使用清单摘要')
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
