# web-design-rl

RL environment pipeline for testing coding agents' ability to replicate multi-page web designs from screenshots.

**Three phases:**
1. **Generate** — DNA → blueprint → design plan → HTML/CSS → screenshots (30 sites, done)
2. **Run** — agent sees screenshots, writes HTML+CSS, verifier renders and scores it
3. **Grade** — visual similarity signals (Phase 3, TBD)

---

## Setup

**Prerequisites:** Python 3.11+, Node.js 18+, Docker, [`uv`](https://docs.astral.sh/uv/)

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Python env
uv sync
source .venv/bin/activate

# Node (for Phase 1 renderer only)
npm install
npx playwright install chromium

# Harbor CLI
uv tool install harbor

# API key
cp .env.example .env   # set ANTHROPIC_API_KEY inside
```

> **Network proxy required** if your machine blocks `api.anthropic.com` via SSL inspection (corporate proxy). See proxy section below.

---

## Phase 1: Generate Websites (already done)

30 sites already generated in `tasks/`. Skip this unless re-generating.

```bash
python scripts/generate.py              # all 30
python scripts/generate.py --ids 001    # specific
python scripts/generate.py --concurrency 3
```

Output per site: `tasks/task_NNN_name/` with `source/`, `screenshots/`, `screenrecordings/` (animated only).

---

## Phase 2: Run Agent

### 1. Package tasks into Harbor format

```bash
python scripts/pack.py          # all 30
python scripts/pack.py --ids 001
python scripts/pack.py --force  # overwrite
```

### 2. Start the proxy (if needed)

Required on machines with corporate SSL inspection. Run in a dedicated tmux window and keep it alive.

```bash
python scripts/proxy.py   # listens on 0.0.0.0:9000, forwards to api.anthropic.com
```

### 3. Run tasks

```bash
python scripts/run.py            # all 30, 4 concurrent
python scripts/run.py -n 8       # 8 concurrent
python scripts/run.py --ids 001  # single task
```

Results are copied to `tasks/task_NNN_name/agent_result/` as each task finishes:
```
tasks/task_001_indian_govt/
  agent_result/
    agent_screenshots/   # rendered PNGs of agent's output
      home.png
      about.png
      ...
    reward.json          # completeness score (0–1)
    checker_detail.json  # per-page breakdown
    agent_log.jsonl      # full Claude Code trajectory
```

### tmux setup (recommended for long runs)

```bash
# Window 1 — proxy
python scripts/proxy.py

# Window 2 — run (Ctrl+b c to open new window)
python scripts/run.py -n 8

# Detach: Ctrl+b d
# Reattach: tmux attach -t harbor
```

---

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

**B** = reference-anchored archetype, **A** = pure AI archetype, 🎬 = CSS animations
