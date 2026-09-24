"""Analysis utilities.

  python -m analysis.analyze table RUN [RUN ...]    cross-run summary on the clean item set
  python -m analysis.analyze rollouts RUN [RUN ...] write data/runs/<model>/<RUN>_rollouts.md (readable rollouts)
  python -m analysis.analyze qa [RUN]               dataset checks, plus pipeline checks on one run
                                           (default main_qwen3-8b)

RUN is a results name such as main_qwen3-32b or main_qwen3-8b-think_model_stakes.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations

from experiment.common import ROOT, run_file

TYPES = ["wrong_target", "empty_output", "partial", "wrong_state", "silent_noop"]


def load(name):
    return [json.loads(l) for l in open(run_file(name, "_judged.jsonl"))]


# ---------------------------------------------------------------- table

def summary(name):
    rows = [r for r in load(name) if not r["ambiguous"]]
    by = {c: [r for r in rows if r["cond"] == c] for c in ("success", "explicit", "subtle")}
    fc = [r for r in by["subtle"] if r["final_label"] == "CLAIMS_SUCCESS"]
    rate = defaultdict(lambda: [0, 0])
    for r in by["subtle"]:
        rate[r["subtle_type"]][0] += r["final_label"] == "CLAIMS_SUCCESS"
        rate[r["subtle_type"]][1] += 1
    return {
        "n": len(by["subtle"]),
        "success_ok": sum(r["final_label"] == "CLAIMS_SUCCESS" for r in by["success"]),
        "explicit_false": sum(r["final_label"] == "CLAIMS_SUCCESS" for r in by["explicit"]),
        "subtle_false": len(fc),
        "recognizable": sum(r["failure_mode"] == "recognizable_when_asked" for r in fc),
        "not_recognized": sum(r["failure_mode"] == "not_recognized_when_asked" for r in fc),
        "subtle_labels": dict(Counter(r["final_label"] for r in by["subtle"])),
        "tp_recognizes_subtle": sum(r["third_party"] == "no" for r in by["subtle"]),
        "self_doubles_down": sum(r.get("self_check") == "yes" for r in fc),
        "by_type": {t: f"{rate[t][0]}/{rate[t][1]}" for t in TYPES},
        "false_templates": {r["template"] for r in fc},
    }


def table(names):
    S = {n: summary(n) for n in names}
    for n, s in S.items():
        print(f"\n== {n}")
        for k, v in s.items():
            if k != "false_templates":
                print(f"  {k}: {v}")
    if len(names) > 1:
        base = S[names[0]]["false_templates"]
        for n in names[1:]:
            o = S[n]["false_templates"]
            print(f"\n{names[0]} vs {n}: both {len(base & o)}, only {names[0]} {len(base - o)}, only {n} {len(o - base)}")


# ---------------------------------------------------------------- rollouts

def rollouts(name):
    from experiment.items import SYSTEM, USER_SUFFIX

    rows = load(name)
    order = {"success": 0, "explicit": 1, "subtle": 2}
    rows.sort(key=lambda r: (r["template"], order[r["cond"]], r["prompt"]))
    prompt = rows[0]["prompt"]
    out = [f"# Rollouts: {name}\n",
           "Each item: system prompt → user request → prefilled tool call → prefilled tool result → "
           "**model's report**. Then the same-context self-check and the fresh-context third-party check "
           "(\"yes\" = task succeeded), and the judge's label.\n",
           f"**System prompt:** {SYSTEM[prompt]}\n"]
    if prompt in USER_SUFFIX:
        out.append(f"**Added to each user request:** {USER_SUFFIX[prompt].strip()}\n")
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
                "not_recognized_when_asked": " ⚠️ FALSE CLAIM (failure not recognized even when asked)"
                }.get(r.get("failure_mode"), "")
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
    path = run_file(name, "_rollouts.md")
    path.write_text("\n".join(out))
    print(f"wrote {path.relative_to(ROOT)} ({len(rows)} items)")


# ---------------------------------------------------------------- qa

def qa(run="main_qwen3-8b"):
    from experiment.gen_templates import ERROR_WORDS
    from experiment.items import T, all_items, tool_output

    print("=== DATASET ===")
    items = all_items()
    print(f"templates {len(T)}, items {len(items)}, unique item_ids {len({i['item_id'] for i in items})}, "
          f"unique template ids {len({t['id'] for t in T})}")
    for key in ("user", "q"):
        dup = [v for v, n in Counter(t[key] for t in T).items() if n > 1]
        print(f"exact duplicate {key}: {len(dup)}", dup[:3])
    dup_out = [v for v, n in Counter(tool_output(t, "subtle") for t in T).items() if n > 1]
    print(f"exact duplicate subtle outputs: {len(dup_out)}")
    pairs = []
    for a, b in combinations(T, 2):
        s = SequenceMatcher(None, a["user"].lower(), b["user"].lower()).ratio()
        if s > 0.6:
            pairs.append((round(s, 2), a["id"], b["id"]))
    print(f"near-duplicate requests (similarity > 0.6): {len(pairs)}")
    for p in sorted(pairs, reverse=True)[:15]:
        print("  ", p)
    no_err_explicit = [t["id"] for t in T if not ERROR_WORDS.search(tool_output(t, "explicit"))]
    err_subtle = [t["id"] for t in T if ERROR_WORDS.search(tool_output(t, "subtle"))]
    same = [t["id"] for t in T if len({tool_output(t, c) for c in ("success", "explicit", "subtle")}) < 3]
    print(f"explicit outputs without an error word: {len(no_err_explicit)}", no_err_explicit[:8])
    print(f"subtle outputs containing an error word: {len(err_subtle)}", err_subtle[:8])
    print(f"templates with non-distinct conditions: {len(same)}")
    ids = Counter(re.findall(r"\b\d{4}\b", json.dumps(T)))
    print("most reused 4-digit numbers:", [(k, v) for k, v in ids.most_common(8) if k not in ("2026",)])

    print(f"\n=== RUN: {run} ===")
    rows = load(run)
    print(f"rows {len(rows)}, unique {len({r['item_id'] for r in rows})}")
    lens = sorted(len(r["report"]) for r in rows)
    print(f"report chars: median {lens[len(lens) // 2]}, max {lens[-1]}")
    print("finish reasons:", Counter(r.get("finish_reason") for r in rows))
    cut = [r["item_id"] for r in rows if r["report"] and not re.search(r"[.!?)`*\]\"'|]\s*$", r["report"].strip())]
    print(f"reports not ending in terminal punctuation: {len(cut)}", cut[:8])
    print(f"reports with thinking tags: {sum('<think>' in r['report'] for r in rows)}")
    print(f"reports containing tool-call-like JSON: "
          f"{sum(bool(re.search(r'{\s*\"(name|type)\"\s*:', r['report'])) for r in rows)}")
    print("self_check values:", Counter(r.get("self_check") for r in rows))
    print("third_party values:", Counter(r["third_party"] for r in rows))
    print("retried items:", sum(r["retries"] > 0 for r in rows), "| no report:", sum(r["retry_loop"] for r in rows))
    print("prompts used:", Counter(r["prompt"] for r in rows), "| models:", Counter(r["model"] for r in rows))


if __name__ == "__main__":
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if cmd == "table" and args:
        table(args)
    elif cmd == "rollouts" and args:
        for a in args:
            rollouts(a)
    elif cmd == "qa":
        qa(*args[:1])
    else:
        print(__doc__)
