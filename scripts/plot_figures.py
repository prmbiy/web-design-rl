#!/usr/bin/env python3
"""Generate figures for assignment.md from EVAL and EVAL'S EVAL data."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT = Path(__file__).parent.parent
FIGS = ROOT / "docs" / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

STYLE = {
    "ours": {"color": "#2563EB", "label": "Ours"},
    "content_only": {"color": "#16A34A", "label": "Content-only"},
    "clip_only": {"color": "#9CA3AF", "label": "CLIP-only"},
    "vlm_only": {"color": "#D97706", "label": "VLM-only"},
    "design2code": {"color": "#DC2626", "label": "Design2Code†"},
}

# ── Figure 1: EVAL scores across all 30 tasks ─────────────────────────────────
def fig_eval_scores():
    scores = []
    for p in sorted(ROOT.glob("tasks/*/evals/report.json")):
        d = json.loads(p.read_text())
        scores.append((d["task"].replace("task_", "").replace("_", " "), d["avg_score"]))
    scores.sort(key=lambda x: x[1], reverse=True)

    names = [s[0] for s in scores]
    vals = [s[1] for s in scores]
    colors = ["#2563EB" if v >= 0.6 else "#60A5FA" if v >= 0.45 else "#BFDBFE" for v in vals]

    fig, ax = plt.subplots(figsize=(14, 7))
    bars = ax.barh(names, vals, color=colors, edgecolor="white", linewidth=0.5)
    ax.axvline(np.mean(vals), color="#1E293B", linestyle="--", linewidth=1.2, label=f"Mean = {np.mean(vals):.3f}")
    ax.set_xlabel("Score", fontsize=12)
    ax.set_title("EVAL: Agent Scores Across 30 Tasks (Claude Code Opus 4.7)", fontsize=13, fontweight="bold")
    ax.set_xlim(0, 1.0)
    ax.legend(fontsize=10)
    ax.invert_yaxis()
    for bar, val in zip(bars, vals):
        ax.text(val + 0.005, bar.get_y() + bar.get_height() / 2, f"{val:.3f}", va="center", fontsize=7.5)
    plt.tight_layout()
    out = FIGS / "eval_scores.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


# ── Figure 2: EVAL score components (topology, content, design) ───────────────
def fig_eval_components():
    tasks, topo, content, design = [], [], [], []
    for p in sorted(ROOT.glob("tasks/*/evals/report.json")):
        d = json.loads(p.read_text())
        tasks.append(d["task"].replace("task_", "").replace("_", " "))
        topo.append(d.get("avg_topology", 0))
        content.append(d.get("avg_content", 0))
        design.append(d.get("avg_design", 0))

    # Sort by overall score
    order = sorted(range(len(tasks)), key=lambda i: (topo[i] * (content[i] + design[i]) / 2), reverse=True)
    tasks = [tasks[i] for i in order]
    topo = [topo[i] for i in order]
    content = [content[i] for i in order]
    design = [design[i] for i in order]

    x = np.arange(len(tasks))
    width = 0.28

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.bar(x - width, topo, width, label="Topology", color="#2563EB", alpha=0.85)
    ax.bar(x, content, width, label="Content", color="#16A34A", alpha=0.85)
    ax.bar(x + width, design, width, label="Design", color="#D97706", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(tasks, rotation=45, ha="right", fontsize=7.5)
    ax.set_ylabel("Score")
    ax.set_title("EVAL: Score Components Per Task", fontsize=13, fontweight="bold")
    ax.set_ylim(0, 1.1)
    ax.legend()
    plt.tight_layout()
    out = FIGS / "eval_components.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


# ── Figure 3: EVAL'S EVAL — rank fidelity per method per page ─────────────────
def fig_evals_eval_rank_fidelity():
    summary_path = ROOT / "bench_results" / "synthetic" / "summary.json"
    if not summary_path.exists():
        print("SKIP fig_evals_eval_rank_fidelity: no data")
        return
    data = json.loads(summary_path.read_text())

    methods = ["ours", "content_only", "vlm_only", "design2code"]
    pages = [e["page"].replace("task_", "").replace("_home", "").replace("_create", "") for e in data]
    rf = {m: [] for m in methods}
    for entry in data:
        for m in methods:
            rf[m].append(entry["result"]["methods"].get(m, {}).get("metrics", {}).get("rank_fidelity", 0))

    x = np.arange(len(pages))
    width = 0.15
    offsets = np.linspace(-2, 2, len(methods)) * width

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, m in enumerate(methods):
        style = STYLE.get(m, {"color": "grey", "label": m})
        ax.bar(x + offsets[i], rf[m], width, label=style["label"], color=style["color"], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(pages, rotation=15, ha="right")
    ax.set_ylabel("Rank Fidelity")
    ax.set_title("EVAL'S EVAL: Rank Fidelity per Method per Page\n(higher = grader correctly orders degraded variants)", fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.15)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=0.8, alpha=0.4)
    ax.legend(fontsize=9)
    fig.text(0.99, 0.01, "†design2code uses image-only block detection (no HTML required)",
             ha="right", fontsize=7, color="grey")
    plt.tight_layout()
    out = FIGS / "evals_eval_rank_fidelity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


# ── Figure 4: EVAL'S EVAL — dynamic span per method ───────────────────────────
def fig_evals_eval_span():
    summary_path = ROOT / "bench_results" / "synthetic" / "summary.json"
    if not summary_path.exists():
        return
    data = json.loads(summary_path.read_text())

    methods = ["ours", "content_only", "vlm_only", "design2code"]
    spans = {m: [] for m in methods}
    for entry in data:
        for m in methods:
            spans[m].append(entry["result"]["methods"].get(m, {}).get("metrics", {}).get("dynamic_span", 0))

    avg_spans = {m: np.mean(spans[m]) for m in methods}
    labels = [STYLE.get(m, {"label": m})["label"] for m in methods]
    colors = [STYLE.get(m, {"color": "grey"})["color"] for m in methods]
    vals = [avg_spans[m] for m in methods]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, vals, color=colors, alpha=0.85, edgecolor="white")
    ax.set_ylabel("Dynamic Span (identity score − blank score)")
    ax.set_title("EVAL'S EVAL: Dynamic Span per Method\n(larger = grader uses more of the [0,1] range)", fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.15)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.3f}", ha="center", fontsize=10)
    plt.tight_layout()
    out = FIGS / "evals_eval_span.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


# ── Figure 5: EVAL'S EVAL — score vs tier (ours vs content_only) ──────────────
def fig_score_vs_tier():
    summary_path = ROOT / "bench_results" / "synthetic" / "summary.json"
    if not summary_path.exists():
        return
    data = json.loads(summary_path.read_text())

    # Use task_030 community events as the example page (most interesting)
    entry = next((e for e in data if "task_030" in e["page"]), data[0])

    variants = entry["result"]["variants"]
    tier_map = {v["name"]: v["tier_index"] for v in variants if not v["is_trap"]}
    name_map = {v["name"]: v["name"].replace("_", " ") for v in variants if not v["is_trap"]}

    methods_to_show = ["ours", "content_only", "vlm_only"]
    fig, ax = plt.subplots(figsize=(12, 5))

    for m in methods_to_show:
        scores_by_tier = {}
        method_scores = entry["result"]["methods"].get(m, {}).get("scores", {})
        for name, tier in tier_map.items():
            if name in method_scores:
                scores_by_tier.setdefault(tier, []).append(method_scores[name])
        tiers = sorted(scores_by_tier.keys())
        avg_scores = [np.mean(scores_by_tier[t]) for t in tiers]
        style = STYLE.get(m, {"color": "grey", "label": m})
        ax.plot(tiers, avg_scores, marker="o", linewidth=2, color=style["color"], label=style["label"])

    tier_labels = {1: "Identity", 2: "Minor\nmutations", 3: "Grayscale", 4: "Section\ndeleted", 5: "Shuffled", 6: "Blank"}
    ax.set_xticks(list(tier_labels.keys()))
    ax.set_xticklabels([tier_labels.get(t, str(t)) for t in tier_labels.keys()])
    ax.set_ylabel("Score")
    ax.set_xlabel("Degradation tier (1 = best, 6 = worst)")
    ax.set_title(f"EVAL'S EVAL: Score vs Degradation Tier\n(page: {entry['page']})", fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out = FIGS / "evals_eval_score_vs_tier.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


# ── Figure 6: Design score distribution across tasks ─────────────────────────
def fig_design_dimensions():
    dims = ["color", "typography", "assets", "proportion", "states"]
    dim_scores = {d: [] for d in dims}

    for p in sorted(ROOT.glob("tasks/*/evals/report.json")):
        d = json.loads(p.read_text())
        for dim in dims:
            dd = d.get("design_dimensions", {}).get(dim, {})
            if dd.get("avg_score") is not None:
                dim_scores[dim].append(dd["avg_score"])

    fig, ax = plt.subplots(figsize=(9, 5))
    positions = range(len(dims))
    bp = ax.boxplot([dim_scores[d] for d in dims], positions=positions, patch_artist=True,
                    medianprops={"color": "white", "linewidth": 2})
    colors = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.set_xticks(positions)
    ax.set_xticklabels([d.capitalize() for d in dims])
    ax.set_ylabel("Score (1–5 scale)")
    ax.set_title("EVAL: Design Dimension Score Distribution Across 30 Tasks", fontsize=12, fontweight="bold")
    ax.set_ylim(0.5, 5.5)
    ax.axhline(3, color="grey", linestyle="--", alpha=0.4, linewidth=1)
    plt.tight_layout()
    out = FIGS / "eval_design_dimensions.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {out}")


if __name__ == "__main__":
    fig_eval_scores()
    fig_eval_components()
    fig_evals_eval_rank_fidelity()
    fig_evals_eval_span()
    fig_score_vs_tier()
    fig_design_dimensions()
    print("\nAll figures saved to docs/figures/")
