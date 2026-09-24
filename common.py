"""Shared OpenRouter client (stdlib only) and model config."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
URL = "https://openrouter.ai/api/v1/chat/completions"
# python.org builds on macOS ship without system CA certs; use the OS bundle.
_SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None)

MODELS = {
    "qwen3-8b": {"id": "qwen/qwen3-8b", "extra": {"reasoning": {"enabled": False}}},
    # Same family, 4x parameters: tests whether 8B's false claims are a capability limit.
    "qwen3-32b": {"id": "qwen/qwen3-32b", "no_think": True,
                  "extra": {"provider": {"order": ["DeepInfra"], "allow_fallbacks": False}}},
    # Same Qwen3 release, ~7x 32B (MoE, 22B active); served only by Alibaba, like 8B.
    "qwen3-235b": {"id": "qwen/qwen3-235b-a22b", "extra": {"reasoning": {"enabled": False}}},
    "qwen3-235b-think": {"id": "qwen/qwen3-235b-a22b", "extra": {"reasoning": {"enabled": True}},
                         "report_max_tokens": 8000, "check_with": "qwen3-235b"},
    # Thinking-mode variants: thinking applies to the report only; recognition checks use `check_with`.
    "qwen3-8b-think": {"id": "qwen/qwen3-8b", "extra": {"reasoning": {"enabled": True}},
                       "report_max_tokens": 8000, "check_with": "qwen3-8b"},
    "qwen3-32b-think": {"id": "qwen/qwen3-32b",
                        "extra": {"provider": {"order": ["DeepInfra"], "allow_fallbacks": False}},
                        "report_max_tokens": 8000, "check_with": "qwen3-32b"},
    # Pin one bf16 provider so every run hits identical weights.
    "llama-3.1-8b": {
        "id": "meta-llama/llama-3.1-8b-instruct",
        "extra": {"provider": {"order": ["CoreWeave"], "allow_fallbacks": False}},
    },
}
JUDGE_MODEL = "anthropic/claude-sonnet-5"

# DeepInfra ignores the API's reasoning switch for Qwen3-32B; configs with no_think=True use Qwen's
# documented soft switch instead (see run.py).
def no_think(messages):
    msgs = [dict(m) for m in messages]
    i = next((k for k, m in enumerate(msgs) if m["role"] == "system"), None)
    if i is None:
        i = max(k for k, m in enumerate(msgs) if m["role"] == "user")
    msgs[i]["content"] = (msgs[i]["content"] or "") + " /no_think"
    return msgs


def _key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("OPENROUTER_API_KEY not found")


def chat(model_id, messages, tools=None, extra=None, temperature=0.0, max_tokens=400, retries=4):
    """Returns (content, raw_message). Raises after `retries` failed attempts."""
    body = {"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools  # no tool_choice: Llama's providers reject it
    body.update(extra or {})
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120, context=_SSL) as r:
                d = json.load(r)
            if "error" in d:
                raise RuntimeError(d["error"])
            msg = d["choices"][0]["message"]
            # Callers get finish_reason/provider alongside the message to detect truncation.
            msg["_finish_reason"] = d["choices"][0].get("finish_reason")
            msg["_provider"] = d.get("provider")
            return (msg.get("content") or "").strip(), msg
        except (urllib.error.URLError, RuntimeError, KeyError, TimeoutError) as e:
            detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)[:300]
            if attempt == retries - 1:
                raise RuntimeError(f"{model_id}: {detail}") from e
            time.sleep(2 ** attempt)
