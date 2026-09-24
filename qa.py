"""Quality checks on the dataset and the main run.  python qa.py"""
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations

from common import ROOT
from gen_templates import ERROR_WORDS
from items import T, all_items, tool_output

print("=== DATASET ===")
items = all_items()
print(f"templates {len(T)}, items {len(items)}, unique item_ids {len({i['item_id'] for i in items})}, "
      f"unique template ids {len({t['id'] for t in T})}")

# exact duplicates
for key in ("user", "q"):
    dup = [v for v, n in Counter(t[key] for t in T).items() if n > 1]
    print(f"exact duplicate {key}: {len(dup)}", dup[:3])
dup_out = [v for v, n in Counter(tool_output(t, "subtle") for t in T).items() if n > 1]
print(f"exact duplicate subtle outputs: {len(dup_out)}")

# near duplicates: request text similarity
pairs = []
for a, b in combinations(T, 2):
    s = SequenceMatcher(None, a["user"].lower(), b["user"].lower()).ratio()
    if s > 0.6:
        pairs.append((round(s, 2), a["id"], b["id"]))
print(f"near-duplicate requests (similarity > 0.6): {len(pairs)}")
for p in sorted(pairs, reverse=True)[:15]:
    print("  ", p)

# condition sanity
no_err_explicit = [t["id"] for t in T if not ERROR_WORDS.search(tool_output(t, "explicit"))]
err_subtle = [t["id"] for t in T if ERROR_WORDS.search(tool_output(t, "subtle"))]
same = [t["id"] for t in T if len({tool_output(t, c) for c in ("success", "explicit", "subtle")}) < 3]
print(f"explicit outputs without an error word: {len(no_err_explicit)}", no_err_explicit[:8])
print(f"subtle outputs containing an error word: {len(err_subtle)}", err_subtle[:8])
print(f"templates with non-distinct conditions: {len(same)}")

# identifier reuse
ids = Counter(re.findall(r"\b\d{4}\b", json.dumps(T)))
print("most reused 4-digit numbers:", [(k, v) for k, v in ids.most_common(8) if k not in ("2026",)])

print("\n=== MAIN RUN ===")
rows = [json.loads(l) for l in open(ROOT / "data/main_qwen3-8b_judged.jsonl")]
print(f"rows {len(rows)}, unique {len({r['item_id'] for r in rows})}, missing {len({i['item_id'] for i in items} - {r['item_id'] for r in rows})}")
lens = sorted(len(r["report"]) for r in rows)
print(f"report chars: median {lens[len(lens)//2]}, max {lens[-1]}")
# ~400 tokens is roughly 1600+ chars; flag long reports and ones not ending in terminal punctuation
long_ = [r["item_id"] for r in rows if len(r["report"]) > 1400]
cut = [r["item_id"] for r in rows if r["report"] and not re.search(r"[.!?)`*\]\"'|]\s*$", r["report"].strip())]
print(f"reports > 1400 chars: {len(long_)}", long_[:5])
print(f"reports not ending in terminal punctuation: {len(cut)}", cut[:8])
think = [r["item_id"] for r in rows if "<think>" in r["report"] or "</think>" in r["report"]]
print(f"reports with thinking tags: {len(think)}")
json_like = [r["item_id"] for r in rows if re.search(r'\{\s*"(name|type)"\s*:', r["report"])]
print(f"reports containing tool-call-like JSON: {len(json_like)}", json_like[:5])
print("self_check values:", Counter(r.get("self_check") for r in rows))
print("third_party values:", Counter(r["third_party"] for r in rows))
odd = [(r["item_id"], r.get("self_raw")) for r in rows if r.get("self_check") == "unclear"] + \
      [(r["item_id"], r["tp_raw"]) for r in rows if r["third_party"] == "unclear"]
print("unclear raw answers:", odd)
long_ans = [(r["item_id"], r["tp_raw"]) for r in rows if len(r["tp_raw"]) > 12] + \
           [(r["item_id"], r.get("self_raw")) for r in rows if len(r.get("self_raw") or "") > 12]
print(f"yes/no answers longer than a word: {len(long_ans)}", long_ans[:5])
print("retried items:", [(r["item_id"], r["retries"], r.get("retry_identical")) for r in rows if r["retries"]])
print("prompts used:", Counter(r["prompt"] for r in rows), "| models:", Counter(r["model"] for r in rows))
