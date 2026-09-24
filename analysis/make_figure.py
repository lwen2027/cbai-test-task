"""Figure: P(claims success | model recognizes the failure when asked), by model, thinking off vs on.

  python -m analysis.make_figure   -> figures/false_claims_by_model.png (+ .svg)

Numerator: subtle-condition false claims whose failure the same model recognizes in the fresh-context
third-party check. Denominator: subtle failures that check recognizes. Clean set (ambiguous templates
excluded). 95% Wilson intervals.
"""
import json
import math

import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path

from experiment.common import ROOT, run_file

MODELS = [("Qwen3-8B", "qwen3-8b"), ("Qwen3-32B", "qwen3-32b"), ("Qwen3-235B", "qwen3-235b")]
MODES = [("Thinking off", "", "#2a78d6"), ("Thinking on", "-think", "#eb6834")]  # palette slots 1, 2

SURFACE, TEXT, TEXT_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def rate(run):
    rows = [json.loads(l) for l in open(run_file(f"main_{run}", "_judged.jsonl"))]
    sub = [r for r in rows if r["cond"] == "subtle" and not r["ambiguous"]]
    recognized = [r for r in sub if r["third_party"] == "no"]
    k = sum(r["final_label"] == "CLAIMS_SUCCESS" for r in recognized)
    return k, len(recognized)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def rounded_bar(ax, x, w, h, color, r_px=8):
    """One path per bar: square baseline, rounded top corners (radius sized from pixels, drawn in data
    units on each axis so it looks circular). A single shape avoids seams between patches."""
    (ax0, ay0), (ax1, ay1) = ax.transData.inverted().transform([(0, 0), (r_px, r_px)])
    rx, ry = min(abs(ax1 - ax0), w / 2), min(abs(ay1 - ay0), h / 2)
    l, r = x - w / 2, x + w / 2
    verts = [(l, 0), (l, h - ry), (l, h), (l + rx, h), (r - rx, h), (r, h), (r, h - ry), (r, 0), (l, 0)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO,
             Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none", zorder=3))


def main():
    data = {}
    for _, m in MODELS:
        for label, suf, _ in MODES:
            data[(m, label)] = rate(m + suf)

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 11})
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(-0.6, len(MODELS) - 0.4)
    ax.set_ylim(0, 0.6)

    ax.set_xticks(range(len(MODELS)))
    ax.set_xticklabels([n for n, _ in MODELS], color=TEXT, fontsize=11.5)
    ax.tick_params(axis="x", length=0, pad=8)
    ax.set_yticks([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ax.set_yticklabels([f"{int(t*100)}%" for t in ax.get_yticks()], color=TEXT_2)
    ax.tick_params(axis="y", length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#b9b8b2")
    ax.set_ylabel("Reported as a success\n(% of recognized failures)", color=TEXT_2, fontsize=10.5)

    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="none") for _, _, c in MODES]
    ax.legend(handles, [l for l, _, _ in MODES], loc="upper left", bbox_to_anchor=(0, 1.1), ncol=2,
              frameon=False, fontsize=10.5, labelcolor=TEXT, handlelength=1.0, handleheight=1.0, columnspacing=1.4)
    fig.text(0.02, 0.012,
             "Of the subtle failures each model correctly identifies as failures when asked in a fresh context,\n"
             "the share it still reported to the user as successes (denominators: 8B 130, 32B 135, 235B 137 of 149).\n"
             "Larger models do no better; reasoning before replying cuts the rate by about two thirds. Error bars: 95% CI.",
             fontsize=8.3, color=TEXT_2, ha="left", va="bottom")
    fig.subplots_adjust(left=0.13, right=0.98, top=0.9, bottom=0.21)
    fig.canvas.draw()  # final layout, so the corner radius converts to the right data units
    bar_w, gap = 0.26, 0.03
    for i, (name, m) in enumerate(MODELS):
        for j, (label, _, color) in enumerate(MODES):
            k, n = data[(m, label)]
            p, lo, hi = wilson(k, n)
            x = i + (j - 0.5) * (bar_w + gap)
            rounded_bar(ax, x, bar_w, p, color)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=TEXT_2, elinewidth=1.2,
                        capsize=4, capthick=1.2, zorder=4)
            ax.text(x, hi + 0.012, f"{p:.0%}", ha="center", va="bottom", color=TEXT, fontsize=11, weight="bold")

    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    fig.savefig(out / "false_claims_by_model.png", facecolor=SURFACE)
    fig.savefig(out / "false_claims_by_model.svg", facecolor=SURFACE)
    for (m, label), (k, n) in data.items():
        p, lo, hi = wilson(k, n)
        print(f"{m:11} {label:12} {k:3}/{n:3} = {p:.1%}  [{lo:.1%}, {hi:.1%}]")


if __name__ == "__main__":
    main()
