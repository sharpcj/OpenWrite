"""Article workspace layout: deliverables at root, process and machinery below.

Three tiers per article directory:
- root: deliverable artifacts (article.html / article.md / cover.png, rednote
  note.md and xhs-*.png, content images referenced by relative paths);
- process/: intermediate creative artifacts (brief, sources, analysis,
  outline discussion, draft, cards, closing);
- workflow/: framework machinery (state, approvals, image contract, manifests,
  publish record).

All path construction goes through path() so controllers, board, skills and
tests share one mapping. migrate() upgrades legacy flat workspaces.
"""
from __future__ import annotations

from pathlib import Path
import shutil

PROCESS_DIR = 'process'
META_DIR = 'workflow'

PROCESS_FILES = frozenset({
    'brief.md', 'sources.json', 'analysis.md', 'outline.md', 'draft.md',
    'cards.md', 'closing.md',
})
META_FILES = frozenset({
    'workflow.json', 'outline.json', 'image-requests.json', 'image-results.json',
    'content-images.json', 'publish-manifest.json', 'publish-record.json',
})


def tier(name: str) -> str:
    if name in PROCESS_FILES:
        return PROCESS_DIR
    if name in META_FILES:
        return META_DIR
    return ''


def path(article: Path, name: str) -> Path:
    """Canonical path for a workspace file; creates tier directories as needed."""
    article = Path(article)
    sub = tier(name)
    target = article / sub / name if sub else article / name
    if sub:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def existing(article: Path, name: str) -> Path:
    """Read-side resolution without side effects: canonical, then legacy flat."""
    article = Path(article)
    sub = tier(name)
    target = article / sub / name if sub else article / name
    if target.exists():
        return target
    flat = article / name
    return flat if flat.is_file() else target


def migrate(article: Path) -> list:
    """Move legacy flat files into their tier; deliverables stay at root."""
    article = Path(article)
    moved = []
    for name in sorted(PROCESS_FILES | META_FILES):
        flat = article / name
        target = path(article, name)
        if flat.is_file() and not target.exists():
            shutil.move(str(flat), str(target))
            moved.append(name)
    moved.extend(_migrate_images(article))
    return moved


def _migrate_images(article: Path) -> list:
    """Unreferenced base/source/candidate images are process artifacts.

    Images named as request outputs (cover, content cards) are deliverables
    and stay at root so relative Markdown links keep working.
    """
    import json
    keep = set()
    for candidate in (article / META_DIR / 'image-requests.json', article / 'image-requests.json'):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding='utf-8'))
                keep = {item.get('output') for item in data.get('images', [])
                        if isinstance(item, dict)}
            except (OSError, ValueError):
                keep = set()
            break
    moved = []
    for file in sorted(article.iterdir()):
        if (file.is_file() and file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
                and file.name not in keep):
            target = article / PROCESS_DIR / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.move(str(file), str(target))
                moved.append(file.name)
    return moved