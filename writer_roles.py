"""Data-driven writer role presets: constraints, gates and skill routing.

Mirrors the formatter-theme / cover-style pattern: each role is a YAML file in
``writer_roles/``. Adding, editing or removing a file changes the selectable
perspectives without code changes. The controller snapshots a role profile into
each task at creation; gates read the snapshot, so later preset edits do not
rewrite the rules of in-flight tasks. Content requirements in ``constraints``
are soft instructions for the writing agent; ``gates`` are the structural
checks the controller enforces.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROLES_DIR = Path(__file__).resolve().parent / 'writer_roles'

# 缺省即现行通用门禁；角色文件可逐项放宽（如 novelist 允许空来源）。
GATE_DEFAULTS = {'sources_required': True, 'source_citations_required': True}


def list_roles() -> list:
    return sorted(path.stem for path in ROLES_DIR.glob('*.yaml'))


def load_role(role: str) -> dict:
    path = ROLES_DIR / f'{role}.yaml'
    if not path.is_file():
        raise ValueError(f'未知写作视角：{role}（可用：{"、".join(list_roles()) or "无"}）')
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'写作视角 {role} 格式不正确（需为映射）')
    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'写作视角 {role} 需有非空 name')
    constraints = data.get('constraints')
    if not isinstance(constraints, str) or not constraints.strip():
        raise ValueError(f'写作视角 {role} 需有非空 constraints')
    aliases = data.get('aliases') or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a.strip() for a in aliases):
        raise ValueError(f'写作视角 {role} 的 aliases 必须是字符串列表')
    gates = data.get('gates') or {}
    if not isinstance(gates, dict) or set(gates) - set(GATE_DEFAULTS):
        raise ValueError(f'写作视角 {role} 的 gates 仅支持 {"、".join(GATE_DEFAULTS)}')
    if not all(isinstance(v, bool) for v in gates.values()):
        raise ValueError(f'写作视角 {role} 的 gates 取值必须为布尔值')
    skills = data.get('skills') or {}
    if not isinstance(skills, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in skills.items()):
        raise ValueError(f'写作视角 {role} 的 skills 必须是「平台: Skill 名」映射')
    return {'role': role, 'name': name.strip(),
            'description': str(data.get('description') or '').strip(),
            'aliases': [a.strip() for a in aliases], 'constraints': constraints.strip(),
            'gates': dict(GATE_DEFAULTS, **gates), 'skills': dict(skills)}


def resolve_role(value: str) -> str:
    """Accept a role id, display name or alias, case-insensitively."""
    text = str(value).strip()
    for role in list_roles():
        data = load_role(role)
        candidates = [role, data['name'], *data['aliases']]
        if text.casefold() in (candidate.casefold() for candidate in candidates):
            return role
    raise ValueError(f'未知写作视角：{text}（可用：{"、".join(list_roles()) or "无"}）')


def labels() -> dict:
    return {role: load_role(role)['name'] for role in list_roles()}


def profile_for(role: str) -> dict:
    """Task-snapshot payload: identity, soft constraints and structural gates."""
    data = load_role(role)
    return {'role': role, 'name': data['name'],
            'constraints': data['constraints'], 'gates': data['gates']}


def validate_profile(value) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get('role'), str) or not value['role'].strip():
        raise ValueError('writer_profile 需含非空 role')
    if not isinstance(value.get('name'), str) or not value['name'].strip():
        raise ValueError('writer_profile 需含非空 name')
    if not isinstance(value.get('constraints'), str) or not value['constraints'].strip():
        raise ValueError('writer_profile 需含非空 constraints')
    gates = value.get('gates')
    if (not isinstance(gates, dict) or set(gates) - set(GATE_DEFAULTS)
            or not all(isinstance(v, bool) for v in gates.values())):
        raise ValueError('writer_profile 的 gates 仅支持布尔值的 sources_required、source_citations_required')
    return value