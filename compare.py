"""Compare runs on the clean item set.  python compare.py main_qwen3-8b main_qwen3-32b ..."""
import json
import sys
from collections import Counter, defaultdict

from common import ROOT

TYPES = ["wrong_target", "empty_output", "partial", "wrong_state", "silent_noop"]


def load(name):
    return [json.loads(l) for l in open(ROOT / f"data/{name}_judged.jsonl")]


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


if __name__ == "__main__":
    names = sys.argv[1:]
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
