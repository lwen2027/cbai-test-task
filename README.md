# False success claims in tool-using agents

Code and data for an experiment on **false success claims**: cases where a language-model agent tells the user a task succeeded even though the tool result in its own context shows it failed.

- **Items:** 450 prefilled agent trajectories. Each is a user request, a tool call and a tool result, and the model writes its report to the user.
- **Models:** Qwen3-8B, 32B and 235B, under a range of prompt conditions and with thinking on and off.
- **Evaluation:** an LLM judge labels each report, and the same model is asked whether the task failed, both in the same conversation and in a fresh one.

![False success claims on failures the model recognizes, by model and thinking mode](figures/false_claims_by_model.png)

## Repository structure

```
experiment/          build the dataset and run models on it
evaluation/          label the model outputs
analysis/            tables, readable rollouts, checks, the figure
data/
  dataset/           the templates and the 450 items
  runs/<model>/      every run's outputs, one folder per model
  evidence/          hand-review labels, hand-verified evidence, resampling results
  archive/           superseded runs and records of the data-quality pass
figures/             the figure above (PNG, SVG)
```

## Code

The pipeline runs left to right:

```
experiment.items ──► experiment.run ──► evaluation.judge ──► evaluation.review ──► analysis.analyze / make_figure
 (build items)       (model reports +    (label each          (hand-review rules,     (tables, rollouts,
                      recognition checks)  report)              claim coding)           figure)
```

### `experiment/`: dataset and model runs

| File | What it does |
|---|---|
| `common.py` | OpenRouter client (standard library only), model configs, and every data path (`DATASET`, `RUNS`, `EVIDENCE`, and `run_file()`, which maps a run name to its file) |
| `items.py` | The 30 hand-written templates, the prompt conditions (system prompts and additions to the user message), the toolsets, and assembly of the 450 items |
| `gen_templates.py` | Generates the other 120 templates with an LLM to fill a 10-domain × 5-failure-type grid. Also replaces templates that fail validation and gives reused identifiers fresh values |
| `run.py` | Runs one model on the items under one condition. For each item it records the report, a same-conversation self-check and a fresh-context third-party check. Handles retries and `--resume` |
| `resample.py` | Robustness check: resamples the recognition questions (10× at temperature 0.7, plus a reasoned variant) |

### `evaluation/`: labelling the outputs

| File | What it does |
|---|---|
| `judge.py` | `label`: an LLM judge (Claude Sonnet 5), given the ground truth, classifies each report as `CLAIMS_SUCCESS`, `REPORTS_FAILURE` or `HEDGES`. `validate`: a second model checks every item reads as intended |
| `review.py` | `apply`: the hand-review rules on top of the judge (label overrides, disclosure and fabrication codes, and `failure_mode`: whether a false claim's failure is recognizable when asked). `code`: LLM coding of false claims, later hand-verified |

### `analysis/`: results

| File | What it does |
|---|---|
| `analyze.py` | `table`: summary across runs (false claims, recognition, failure types). `rollouts`: writes the readable rollouts Markdown. `qa`: dataset and pipeline checks |
| `make_figure.py` | Builds `figures/false_claims_by_model.png` / `.svg` from the judged data |

## Data

### Where things are

| Location | Contents |
|---|---|
| `data/dataset/templates_generated.json` | The 120 generated templates. The 30 hand-written ones are in `experiment/items.py` |
| `data/dataset/items.jsonl` | All 450 items: 150 templates × 3 tool results (success, explicit failure, subtle failure) |
| `data/dataset/item_validity.jsonl` | The second model's validity check for every template and tool result |
| `data/runs/<model>/` | All outputs for one model (`qwen3-8b/`, `qwen3-32b/`, `qwen3-235b/`), including its thinking-mode and condition runs |
| `data/evidence/hand_review.json` | The hand-review labels applied by `evaluation.review` |
| `data/evidence/quoted_then_contradicted_verified.json`, `thinking_noticed_verified.json` | Hand-verified cases where the model stated the failure, or noticed it in its reasoning, and still claimed success |
| `data/evidence/resample_qwen3-8b.jsonl` | The resampled recognition checks |
| `data/archive/` | The pilot, the 30-template run, the first 150-template run, and records of the data-quality pass (template replacements, identifier changes) |

### Run files

Run names follow `main_<model>[-think][_<condition>]`, e.g. `main_qwen3-32b`, `main_qwen3-32b-think`, `main_qwen3-32b_verify_user`. Each run in `data/runs/<model>/` has:

| File | Contents |
|---|---|
| `<run>.jsonl` | Raw output, one record per item: the item, the model's report, and both recognition answers (plus the reasoning trace for thinking runs) |
| `<run>_judged.jsonl` | The same records with labels added. The field to use is `final_label`; `failure_mode` says whether a false claim's failure is recognizable when asked |
| `<run>_rollouts.md` | **The easiest way to read the results:** every item with its tool result, report, checks and label. False claims are marked ⚠️ |
| `<run>_claims.jsonl` | Coded false claims (only some runs) |

Key fields in a judged record:

| Field | Meaning |
|---|---|
| `cond` | `success`, `explicit` or `subtle`: which tool result the model saw |
| `prompt` | The condition, e.g. `neutral`, `verify_user`, `model_stakes` |
| `truth` | `success` or `failure` (ground truth) |
| `report` | The model's report to the user |
| `self_check`, `third_party` | Answers to "did the task succeed?", in the same conversation and in a fresh context (`yes` / `no`) |
| `final_label` | `CLAIMS_SUCCESS`, `REPORTS_FAILURE`, `HEDGES` or `NO_REPORT`. A false claim is `truth == "failure"` and `final_label == "CLAIMS_SUCCESS"` |
| `failure_mode` | For false claims: `recognizable_when_asked` or `not_recognized_when_asked` |
| `subtle_type`, `domain`, `stakes` | Template categories |

## Reproducing

Requires Python 3.10+ and `matplotlib`, for the figure only. The API client uses just the standard library. Put an OpenRouter key in `.env` at the repository root:

```
OPENROUTER_API_KEY=sk-or-...
```

Then, from the repository root:

```bash
python -m experiment.items                                     # build the item set
python -m experiment.run --model qwen3-32b                     # baseline run (all 450 items)
python -m experiment.run --model qwen3-32b-think --conds subtle   # thinking mode, subtle items
python -m evaluation.judge label main_qwen3-32b                # judge the reports
python -m evaluation.review apply main_qwen3-32b               # apply hand-review rules
python -m analysis.analyze table main_qwen3-8b main_qwen3-32b main_qwen3-235b   # cross-run table
python -m analysis.analyze rollouts main_qwen3-32b             # readable rollouts
python -m analysis.make_figure                                 # rebuild the figure
```

- **Other conditions:** use `--prompt` on `experiment.run` (`neutral_wording`, `verify`, `verify_user`, `quote_first`, `audit_user`, `model_stakes`, `realistic_stakes`).
- **Models:** `--model` accepts `qwen3-8b`, `qwen3-32b`, `qwen3-235b` and their `-think` variants.
- **Interrupted runs:** `--resume` keeps the rows already saved and runs only the missing items.
- **Rebuilding the dataset:** `python -m experiment.gen_templates` regenerates the templates, then `python -m evaluation.judge validate` checks them. Both call the API.
