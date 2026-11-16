# OpenWrite

[中文](README.md) · [English](README.en.md)

OpenWrite is a project-local WeChat article workspace for AI agents. **Open this repository in your agent and use the skills included in the project. No global skill installation is required.**

## Start writing

Open the repository as the working directory. Read [AGENTS.md](AGENTS.md), then describe your task. If your host does not automatically load project instructions, explicitly ask it to read that file first. `CLAUDE.md` and `GEMINI.md` point to the same entrypoint rather than maintaining separate workflows.

Examples:

> Write a WeChat article about RAG for nontechnical readers. Save it under articles/rag-guide, including illustrations and formatted HTML.

> Continue articles/rag-guide and simplify the introduction.

> Upload articles/rag-guide to the WeChat draft box with the title “How knowledge bases help AI answer accurately”.

Project instruction loading depends on the host. Search, file access, shell execution, and image generation depend on the tools it provides. Missing capabilities are reported explicitly. See [AGENT_GUIDE.md](AGENT_GUIDE.md#english).

## Layout

```text
OpenWrite/
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── AGENT_GUIDE.md
├── openwrite.py
├── workflow.py
├── preferences.py
├── platforms.py          # platform adapter registry
├── .env.example        # tracked placeholder template
├── .env                # local real config, created by setup, Git-ignored
├── requirements.txt
├── skills/
│   ├── wechat-blogger-writer/
│   ├── wechat-tech-writer/
│   ├── wechat-product-manager-writer/
│   ├── rednote-note-writer/
│   ├── wechat-article-formatter/
│   ├── wechat-draft-publisher/
│   └── openwrite-images/
├── articles/
└── tests/
```

The original four skill names remain unchanged. The new `openwrite-images` capability handles image acquisition independently of writing. The project reads them on demand from `skills/`; do not copy them into a user-level skill directory.

## Setup and commands

Python 3.8+ is required for the core scripts.

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python3 -m pip install -r requirements.txt
python3 openwrite.py doctor
# Required only for uploading drafts: create the local config and fill in credentials
python3 openwrite.py setup

python3 openwrite.py new rag-guide --title "RAG explained" --type tech
# Use --type product for the product manager perspective.
python3 openwrite.py workflow status articles/rag-guide
# Submit the first five stages through workflow complete --step <stage>.
# Before draft: present three candidate titles plus an outline and get user approval
# (outline.md / outline.json); skip only when authorized via OutlineApproval=false or --skip-outline.
# After the first five stages have passed their checks:
python3 openwrite.py workflow finalize articles/rag-guide   # stage 6: article.md
python3 openwrite.py format articles/rag-guide --theme default  # stage 7: publishable artifact
# Preserve original quotes and spacing, including code examples:
python3 openwrite.py format articles/rag-guide --no-preformat

# Only after the user confirms publication; calls the WeChat API and creates a draft.
# The title defaults to the approved value in publish-manifest.json:
python3 openwrite.py publish articles/rag-guide
```

`doctor` performs local checks only. `new` creates a brief, source list, analysis and draft stubs, and `workflow.json`; it does not create final Markdown. The agent writes the article using the selected skill and submits completed artifacts through the workflow. Existing article directories are not overwritten. `format` is the seventh stage: it runs the formatter and code-block converter, checks publishability, writes `publish-manifest.json`, and preserves existing HTML on failure. Themes: `default`, `grace`, `modern`, `simple`.

## Article workspace

Each article lives in `articles/<name>/`: `brief.md` records requirements; `workflow.json` stores progress; `sources.json` stores source content; `analysis.md` cites source IDs; `outline.md` and `outline.json` record the approved title and outline; `draft.md` contains the body; `article.md` is assembled in stage six; `cover.png` is uploaded separately; `structure.png` is an optional content illustration; other images are optional; `article.html` and `publish-manifest.json` are the stage-seven publishable artifact.

All three writing perspectives follow this fixed sequence: **Search sources → Analyze sources → Write the body → Generate the cover → Generate content illustrations as needed → Generate Markdown → Format and save the publishable artifact**. Structure diagrams are optional content illustrations. Completing stage seven means the artifact is publishable; uploading still requires explicit user confirmation. Continue an existing article by reading its brief and artifacts. Article workspaces are ignored by Git by default.

## External services

Writing skills define visual requirements only: content, dimensions, palette, composition, text, placement, and acceptance criteria. The independent [openwrite-images](skills/openwrite-images/SKILL.md) capability obtains and validates files. They exchange `image-requests.json` and `image-results.json` in each article directory; see the [contract](docs/image-contract.md).

```bash
python3 openwrite.py image articles/rag-guide --id cover --backend comfyui
python3 openwrite.py image articles/rag-guide --id cover --backend file --source /path/to/cover.png
```

Backend code, configuration, and workflows live only in `skills/openwrite-images/`. ComfyUI and optional Gemini / DALL-E implementations are retained. Agent-generated, user-supplied, or software-rendered images can be imported through `file`. Text-precise cards (Rednote) are typeset in HTML and screenshotted by the `html` backend using Playwright, with real DOM checks for overflow, minimum font size and safe area. Pillow validates files and dimensions. Resizing, cropping, and overwriting require explicit options. File readiness does not replace visual review by the writing workflow.

Rednote card rendering needs Playwright plus a one-time browser download (`python3 -m playwright install chromium`); it runs locally and offline afterwards. `doctor` reports its readiness. WeChat-only tasks do not need it.

WeChat credentials share the project configuration: `.env.example` is a tracked placeholder template, and real values live in the local `.env`. Run `python3 openwrite.py setup` to copy the template (existing files are never overwritten; the copy gets mode 600 and is Git-ignored), then fill in `WeChatAppID`, `WeChatAppSecret`, and optionally `WeChatAuthor`. Never put real secrets into `.env.example`. Without credentials, `publish` fails with these instructions instead of reading `~/.wechat-publisher/config.json`; the access-token cache remains at `~/.wechat-publisher/token_cache.json`. Project-local skills do not remove external-service setup requirements. Publishing creates a WeChat draft rather than sending the article to subscribers.

## Validation and attribution

```bash
python3 -m unittest discover -s tests -v
```

Legacy live preview and batch scripts still need adaptation to the current formatter. The project command uses the maintained core conversion scripts.

Forked from [BND-1/wechat_article_skills](https://github.com/BND-1/wechat_article_skills), previously adapted for Hermes Agent, and now organized as OpenWrite with a project-local agent workflow. [MIT License](LICENSE).

## Step-by-step workflow

The overall flow has three modules: **request → writing → publishing**. The request and the upload need explicit user confirmation; writing is a seven-stage pipeline whose deliverable is a publishable artifact.

The seven stages are `search`, `analysis`, `draft`, `cover`, `content`, `markdown`, and `format`. Use `workflow complete <article> --step <stage>` for the first five; `finalize` completes the sixth and `format` completes the seventh. Each transition validates required artifacts and checks the fingerprints of prior stages. Image stages require actual visual review, confirmed with `--reviewed --note "review details"`. If content images are unnecessary, explicitly record `needed: false` and a reason in `content-images.json`.

Between analysis and draft there is a **title and outline checkpoint**: present three candidate titles (at least one bold/suspenseful `激进悬念`, one objective/neutral `客观中性`, the third defaults to benefit-oriented `利益实用`) plus an outline, let the user pick or define a title and approve the outline, and iterate on feedback until approved. Only then write the full body. The approval is recorded in `outline.md` and `outline.json`; the draft H1 must match the approved title. The checkpoint is controlled by `OutlineApproval` in `.env` (default on) and can be skipped with `new --skip-outline` when the user authorizes it.

`workflow finalize <article>` assembles `draft.md` and approved images into `article.md`. Content image `placement` must uniquely match a complete heading line or paragraph in the draft. Covers are excluded from the body.

`format <article>` is the seventh stage: it converts HTML, runs the WeChat code-block conversion, then checks publishability (title ≤64 chars / 192 bytes, author ≤20 bytes, digest ≤120 bytes, PNG cover under 2MB, non-empty HTML, converted code blocks, existing local images). On success it writes `publish-manifest.json` with metadata and fingerprints of every artifact and completes the stage; on failure it preserves the previous HTML. Re-running `format` with another theme replaces the seventh record. `publish` requires the manifest fingerprints to match the current artifacts, takes the title from the manifest unless overridden, and refuses stale or modified output.

Use `workflow status <article>` to resume in another session. Use `workflow reset <article> --from draft` to redo the body and later stages without deleting files. Existing articles can start with `workflow init <article>`, then submit their artifacts in order. See the [stage protocol](docs/workflow.md) for JSON examples and exact checks. These are project command gates, not permission isolation or automatic editorial review.

## Platform and perspective defaults

Runtime configuration is read only from the local `.env`; `.env.example` is a sample template used solely by `setup` and never participates in resolution. Without `.env` there are no defaults and the command asks for an explicit choice. The template samples WeChat and the self-media blogger perspective. Platform keys are `WeChat` and `Rednote`; perspective keys are `SelfMediaBlogger`, `TechWriter`, and `ProductManager`.

Explicit user choices, passed by the agent as `--platform wechat|rednote` and `--perspective blogger|tech|product`, override the unique enabled default in each group. If no single option is enabled and the user has not specified one, the command refuses to create a task and asks for an explicit choice. The two groups resolve independently.

Run `python3 openwrite.py preferences` to inspect the resolved defaults. Task choices are persisted in `workflow.json`; changing the defaults does not change existing work. Rednote has P0 implemented (writing and card artifacts); its upload adapter is not implemented, so publishing is manual. See [selection rules](docs/task-selection.md).

Platform differences live in the `platforms.py` registry (artifact shape, dimensions, image counts, limits, renderer and publisher skills); the controller and command entry only read that table. `implemented` covers writing through the publishable artifact, `publish_implemented` covers uploading; the two are independent. See the [platform adapter contract](docs/platforms.md) for the onboarding checklist and phased roadmap.
