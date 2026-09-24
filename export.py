"""Render judged rollouts as readable Markdown: python export.py main_qwen3-8b"""
import json
import sys

from common import ROOT
from items import SYSTEM

name = sys.argv[1]
rows = [json.loads(l) for l in open(ROOT / f"data/{name}_judged.jsonl")]
order = {"success": 0, "explicit": 1, "subtle": 2}
rows.sort(key=lambda r: (r["template"], order[r["cond"]], r["prompt"]))

out = [f"# Rollouts: {name}\n",
       "Each item: system prompt (neutral or pressure) → user request → prefilled tool call → prefilled tool result → "
       "**model's report**. Then the same-context self-check and the fresh-context third-party check "
       "(\"yes\" = task succeeded), and the judge's label.\n",
       f"**Neutral system prompt:** {SYSTEM['neutral']}\n",
       f"**Pressure adds:** {SYSTEM['pressure'][len(SYSTEM['neutral']):].strip()}\n"]
current = None
for r in rows:
    if r["template"] != current:
        current = r["template"]
        out += [f"\n---\n\n## {current}  ({r['domain']}, subtle={r['subtle_type']}, stakes={r['stakes']}, "
                f"{'generated' if r.get('generated') else 'hand-written'})\n",
                f"**User:** {r['user']}  ",
                f"**Tool call:** `{r['tool']}({json.dumps(r['args'])})`  ",
                f"**Recognition question:** {r['q']}\n"]
    flag = {"recognizable_when_asked": " ⚠️ FALSE CLAIM (failure recognizable when asked)",
            "not_recognized_when_asked": " ⚠️ FALSE CLAIM (failure not recognized even when asked)"}.get(r.get("failure_mode"), "")
    if r.get("ambiguous"):
        flag += " (ambiguous item, excluded from clean analysis)"
    override = f" (judge said {r['label']})" if r["final_label"] != r["label"] else ""
    out += [f"### {r['cond']} / {r['prompt']} → **{r['final_label']}**{override}{flag}\n",
            f"Tool result:\n```\n{r['tool_output']}\n```",
            "Report" + (f" (after {r['retries']} retries)" if r["retries"] else "") + ":",
            "> " + (r["report"] or "(no report)").replace("\n", "\n> ") + "\n",
            f"Self-check: `{r.get('self_check')}` · Third-party: `{r['third_party']}` · "
            + (f"disclosed: `{r['disclosed']}` · fabricated (hand): `{r['fabricated_hand']}` · "
               if r["cond"] == "subtle" and r.get("disclosed") is not None else "")
            + f"promises_action: `{r['promises_action']}`  ",
            f"Judge: {r['why']}\n"]

path = ROOT / f"data/{name}_rollouts.md"
path.write_text("\n".join(out))
print(f"wrote {path.relative_to(ROOT)} ({len(rows)} items)")
