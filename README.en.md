# OpenWrite

[中文](README.md) · [English](README.en.md)

OpenWrite is a project-local content workspace for AI agents, supporting WeChat articles and Rednote image notes. It covers research, writing, images, publishable artifacts, and publishing on request, with sources and results saved inside the project.

**Open the repository in your agent to use its built-in skills. No global skill installation is required.** The agent researches, creates and reviews; code validates artifacts and stage order.

| Platform | Deliverables | Publishing |
|---|---|---|
| WeChat | Markdown, formatted HTML, a separate cover and optional body images | Upload to the draft box; send to subscribers through the WeChat backend |
| Rednote | Caption text and 3:4 cards, with a cover as the first card and required content cards | Publish privately by default; public visibility needs explicit authorization |

## Quick start

On macOS / Linux, install Python 3.9+ (3.10+ recommended) and Make, then run from the repository root:

```bash
make setup
make doctor
```

`make setup` creates or reuses `.venv`, installs dependencies, and copies `openwrite.example.yaml` to local `openwrite.yaml` without overwriting existing configuration. Dependency installation needs network access. It does not fill credentials, generate images or publish anything.

Edit `openwrite.yaml` for platforms, accounts, writer role and optional service credentials. Each platform can hold multiple accounts under `wechat.accounts` / `rednote.accounts`, keyed by generic names such as `账号1` / `账号2`; a platform is enabled when it has at least one account (`enabled: false` pauses it). The account key is the identifier used by `--account` and task snapshots; each account also accepts an optional `name` string for human recognition — Official account name (user-filled) on WeChat, Account name (user-filled) on Rednote. Settings merge in the order `defaults` → platform section → account → task snapshot; credentials, writer role, cover style and format theme are isolated per account. The template enables WeChat with the blogger role. WeChat also supports technical, product-manager, news-reporter and novelist perspectives (data-driven presets in `writer_roles/`, overridable per account); Rednote only supports the blogger role. Configure image sources under `image_sources` and publishing credentials before using them.

Rednote card rendering and publishing additionally need a one-time browser download:

```bash
.venv/bin/python -m playwright install chromium
```

See [environment and runtime setup](docs/setup.md) for manual installation, Windows PowerShell, board usage and troubleshooting. `doctor` performs local checks only; it does not validate external services or credentials. Detailed project guides are maintained in Chinese.

## Start writing

Open the repository as the working directory and describe your request:

> Write a WeChat article about RAG for nontechnical readers, including images and formatted HTML.

> Create a Rednote image note about three ways to organize reading notes, including cards and caption text.

> Continue articles/rag-guide, simplify its introduction and format it again.

> Upload articles/rag-guide to the WeChat draft box.

All formal project rules start in [AGENT_GUIDE.md](AGENT_GUIDE.md). `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` only direct the host to that guide. If the host does not load instructions automatically, ask the agent to read `AGENT_GUIDE.md` first.

Writing follows seven stages: research, analysis, draft, cover, content images, Markdown and publishable artifacts. By default, the title and outline require approval before the full draft is written. Writing and formatting do not authorize publishing. Available search, file, shell and image tools depend on the host; missing capabilities are reported without claiming unfinished work is complete.

## Workspaces and progress

Each task lives in its own `articles/<name>/`, ignored by Git by default:

```text
articles/<name>/
├── article.md / article.html / cover.png  # WeChat artifacts + optional body images
├── note.md / xhs-*.png                   # Rednote artifacts (platform-specific)
├── process/                             # Brief, sources, analysis, outline and drafts
└── workflow/                            # State, image records and publish manifest
```

The read-only board shows progress and artifact previews. Double-click `看板.command` / `看板.sh` / `看板.bat` (macOS / Linux / Windows) to start it and open a browser; closing the script window stops it. See [board controls](docs/setup.md#实时故事板) for manual use and ports. Resume a task with:

```bash
.venv/bin/python openwrite.py workflow status articles/rag-guide
```

## Documentation

| Document | Purpose |
|---|---|
| [Agent guide](AGENT_GUIDE.md) | Formal execution rules, skill routing, approvals and delivery |
| [Environment and runtime](docs/setup.md) | Installation, credentials, Python environment, formatting, board and troubleshooting |
| [Task selection](docs/task-selection.md) | Platform/role precedence, arguments and saved choices |
| [Seven-stage workflow](docs/workflow.md) | Artifact schemas, JSON examples, publish checks and rework commands |
| [Image contract](docs/image-contract.md) | Requests, results, sources and review records |
| [WeChat cover design](docs/cover-style.md) | Layout, visual style, color tone and per-task overrides |
| [Platform adapter contract](docs/platforms.md) | Platform specs, code responsibilities and adapter onboarding |

## Development checks

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The command entrypoint is `openwrite.py`; skills live in `skills/`, platform specs in `platforms.py`, and workspace paths in `layout.py`. Engineering requests modify the project directly without starting article production.

## License

[MIT License](LICENSE).
