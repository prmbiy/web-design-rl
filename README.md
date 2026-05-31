# web-design-rl

RL environment pipeline for testing coding agents' ability to replicate multi-page web designs.

## Overview

Three phases:
1. **Generate** — create ground-truth websites from scratch (DNA → blueprint → design plan → HTML/CSS → screenshots)
2. **Harbor task** — package as Harbor tasks that agents receive screenshots and must replicate
3. **Grade** — render agent output and compare to ground truth using 5 continuous signals

See [docs/CONTEXT.md](docs/CONTEXT.md) for full project context, [docs/PLAN_phase1.md](docs/PLAN_phase1.md) for Phase 1, and [docs/PLAN_phase2.md](docs/PLAN_phase2.md) for Phase 2.

## Setup

### Prerequisites
- [uv](https://docs.astral.sh/uv/) — Python package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 18+
- Docker — required to build and run Harbor tasks
- ffmpeg (for screen recordings — `brew install ffmpeg` or `apt install ffmpeg`)

### Install

```bash
# Python environment
uv sync                          # creates .venv and installs all Python deps
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# Node.js renderer
npm install                      # installs Playwright
npx playwright install chromium  # downloads headless Chromium

# Harbor task runner (installs the `harbor` CLI globally via uv)
uv tool install harbor

# API key
cp .env.example .env             # then edit .env and set ANTHROPIC_API_KEY
```

## Phase 1: Generate Websites

```bash
# List all 30 DNA archetypes
python scripts/generate.py --list

# Generate all 30 sites
python scripts/generate.py

# Generate specific sites
python scripts/generate.py --ids 001 002 003

# Run in parallel (3 concurrent)
python scripts/generate.py --concurrency 3

# Force regenerate (ignore cache)
python scripts/generate.py --force

# Re-run a single step
python scripts/generate.py --ids 001 --step blueprint
python scripts/generate.py --ids 001 --step renderer
```

Output for each site is written to `tasks/task_{id}_{name}/`:
```
tasks/task_001_indian_govt/
  site_dna.json           # copy of source DNA
  blueprint.json          # fictional content spec
  design_plan.json        # visual design spec
  source/                 # HTML/CSS ground truth
    home.html
    about.html
    ...
  screenshots/            # ground truth PNGs (1440px wide)
    home.png
    about.png
    ...
  screenrecordings/       # only for animated sites
    home.mp4
    ...
  generation_complete.json
```

## Phase 2: Package Harbor Tasks

Wraps each Phase 1 task directory into a Harbor task. Requires Phase 1 output to exist first.

```bash
# Package all completed tasks
python scripts/pack.py

# Package specific tasks
python scripts/pack.py --ids 001 016

# Force overwrite existing harbor/ dirs
python scripts/pack.py --force
```

Each task gets a `harbor/` directory alongside its Phase 1 output:
```
tasks/task_001_indian_govt/
  harbor/
    instruction.md              # what the agent sees
    task.toml                   # Harbor metadata
    environment/
      Dockerfile                # Node 22 + Playwright + ground-truth screenshots
      task_screenshots/         # ground-truth PNGs baked into image
        home.png
        about.png
        ...
      task_screenrecordings/    # only for animated sites
      checker/
        run.py                  # completeness checker (not the real grader)
    solution/
      site/                     # oracle HTML files
      solve.sh
    tests/
      test.sh
```

To run a task with Harbor:
```bash
# Make sure ANTHROPIC_API_KEY is set
export ANTHROPIC_API_KEY=sk-ant-...   # or load from .env

# Run the agent on a single task (claude-code agent, opus model)
harbor run \
  -p tasks/task_001_indian_govt/harbor \
  -a claude-code \
  -m claude-opus-4-7 \
  --ae ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

# Run multiple tasks with 4 concurrent trials (default)
harbor run \
  -p tasks/task_001_indian_govt/harbor \
  -p tasks/task_002_japanese_news/harbor \
  -a claude-code \
  -m claude-opus-4-7 \
  --ae ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -n 4

# Run N attempts per task (for statistical robustness)
harbor run \
  -p tasks/task_001_indian_govt/harbor \
  -a claude-code \
  -m claude-opus-4-7 \
  --ae ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -k 3
```

Job results land under `jobs/<job_id>/`. Agent screenshots are at
`jobs/<job_id>/harbor__<trial>/verifier/agent_screenshots/`.

The agent (Claude Code) sees the screenshots, writes HTML to `/app/site/`. After it finishes, the verifier renders the agent's output with Playwright and saves screenshots to `/logs/verifier/agent_screenshots/` for Phase 3 comparison.

## DNA Archetypes (30 sites)

| ID | Name | Type | Animated |
|---|---|---|---|
| 001 | Indian government portal | B | |
| 002 | Japanese dense news site | B | |
| 003 | Craigslist-style classifieds | B | |
| 004 | Ad-heavy tabloid | B | |
| 005 | Early-2000s corporate | B | 🎬 |
| 006 | Nigerian fintech | B | |
| 007 | Latin American telco | B | |
| 008 | Hacker News clone | B | |
| 009 | Retro phpBB forum | B | |
| 010 | Russian e-commerce | B | |
| 011 | Korean beauty brand | B | 🎬 |
| 012 | NHS health portal | B | |
| 013 | Australian real estate | B | |
| 014 | Indian food delivery | B | |
| 015 | Crypto project page | B | 🎬 |
| 016 | SaaS dark mode | B | 🎬 |
| 017 | Brutalist agency portfolio | B | 🎬 |
| 018 | Luxury fashion editorial | B | 🎬 |
| 019 | Esports/gaming hub | B | 🎬 |
| 020 | Developer docs site | B | |
| 021 | Niche B2B SaaS | A | |
| 022 | Indie developer portfolio | A | 🎬 |
| 023 | Non-profit climate org | A | |
| 024 | Urban coworking space | A | |
| 025 | Indie podcast network | A | |
| 026 | Yoga/wellness studio | A | 🎬 |
| 027 | Hardware startup | A | |
| 028 | Academic research lab | A | |
| 029 | Local restaurant group | A | |
| 030 | Community events platform | A | 🎬 |

**B** = reference-anchored archetype, **A** = pure AI archetype, 🎬 = includes CSS animations
