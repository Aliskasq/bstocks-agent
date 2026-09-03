"""OpenRouter LLM gateway with a real tool-calling loop.

The model never touches Binance directly: it may only request tools that we
registered. Every call and result is written into the Trace.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx

from ..config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_URL
from ..trace import Trace


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Runtime override chosen from the dashboard. Empty = fall back to .env value.
_ACTIVE_MODEL: str = ""


def active_model() -> str:
    return _ACTIVE_MODEL or OPENROUTER_MODEL


def set_active_model(model: str) -> str:
    """Switch the model used by every subsequent cycle. Not persisted."""
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = (model or "").strip()
    return active_model()


_MODELS_CACHE: dict[str, Any] = {}


def list_models(*, free_only: bool = True, tools_only: bool = True,
                refresh: bool = False) -> list[dict]:
    """Catalogue of models available to our key.

    free_only  -> prompt and completion price are both exactly 0
    tools_only -> model advertises tool-calling, which the agent requires
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set (.env)")

    if refresh or "data" not in _MODELS_CACHE:
        with httpx.Client(timeout=30) as c:
            r = c.get(OPENROUTER_MODELS_URL,
                      headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"})
        if r.status_code >= 400:
            raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {r.text[:200]}")
        _MODELS_CACHE["data"] = r.json().get("data", [])

    out = []
    for m in _MODELS_CACHE["data"]:
        pricing = m.get("pricing") or {}
        try:
            prompt_p = float(pricing.get("prompt") or 0)
            compl_p = float(pricing.get("completion") or 0)
        except (TypeError, ValueError):
            continue
        is_free = prompt_p == 0 and compl_p == 0
        has_tools = "tools" in (m.get("supported_parameters") or [])
        if free_only and not is_free:
            continue
        if tools_only and not has_tools:
            continue
        out.append({
            "id": m.get("id"),
            "name": m.get("name") or m.get("id"),
            "context_length": m.get("context_length"),
            "free": is_free,
            "tools": has_tools,
        })
    out.sort(key=lambda x: -(x.get("context_length") or 0))
    return out


class ToolRegistry:
    def __init__(self) -> None:
        self._fns: dict[str, Callable[..., Any]] = {}
        self._schemas: list[dict] = []

    def register(self, name: str, description: str, parameters: dict,
                 fn: Callable[..., Any]) -> None:
        self._fns[name] = fn
        self._schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        })

    @property
    def schemas(self) -> list[dict]:
        return self._schemas

    def call(self, name: str, args: dict) -> Any:
        if name not in self._fns:
            return {"error": f"unknown tool {name}"}
        return self._fns[name](**args)


RETRY_STATUS = {429, 500, 502, 503, 520, 524}


def _post_chat(payload: dict, trace: Trace, *, attempts: int = 4) -> dict:
    """POST to OpenRouter, retrying on shared-pool 429s.

    Free models sit in a shared upstream pool and return 429 regularly. We back
    off, then fall back to another free tool-calling model rather than aborting
    the whole cycle.
    """
    model = payload["model"]
    tried: list[str] = []
    delay = 3.0

    for attempt in range(attempts):
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "X-Title": "bStocks AI Agent",
                },
                json=payload,
            )
        if resp.status_code < 400:
            return resp.json()
        if resp.status_code not in RETRY_STATUS or attempt == attempts - 1:
            raise RuntimeError(
                f"OpenRouter HTTP {resp.status_code}: {resp.text[:400]}")

        tried.append(payload["model"])
        retry_after = resp.headers.get("retry-after")
        wait = float(retry_after) if (retry_after or "").isdigit() else delay
        trace.add("status",
                  status=f"{payload['model']} returned {resp.status_code}; "
                         f"retry in {wait:.0f}s")
        time.sleep(wait)
        delay = min(delay * 2, 30)

        # After the first failed retry, try a different free model.
        if attempt >= 1:
            try:
                alts = [m["id"] for m in list_models(free_only=True,
                                                     tools_only=True)]
            except Exception:  # noqa: BLE001
                alts = []
            nxt = next((m for m in alts if m not in tried and m != model), None)
            if nxt:
                payload["model"] = nxt
                trace.add("status", status=f"falling back to {nxt}")

    raise RuntimeError("OpenRouter: exhausted retries")


def chat_with_tools(messages: list[dict], registry: ToolRegistry, trace: Trace,
                    *, max_rounds: int = 8, model: str | None = None,
                    response_json: bool = False) -> dict:
    """Run the tool-calling loop until the model returns a final answer."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set (.env)")

    model = model or active_model()
    convo = list(messages)

    for round_i in range(max_rounds):
        payload: dict[str, Any] = {
            "model": model,
            "messages": convo,
            "tools": registry.schemas,
            "tool_choice": "auto",
        }
        if response_json and round_i > 0:
            payload["response_format"] = {"type": "json_object"}

        data = _post_chat(payload, trace)
        choice = data["choices"][0]
        msg = choice["message"]
        convo.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if msg.get("content"):
            trace.llm("assistant", msg["content"])

        if not tool_calls:
            return {"content": msg.get("content", ""), "messages": convo,
                    "usage": data.get("usage")}

        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            trace.tool_call(name, args)
            try:
                result = registry.call(name, args)
            except Exception as exc:  # noqa: BLE001
                result = {"error": f"{type(exc).__name__}: {exc}"}
            trace.tool_result(name, result)
            convo.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, default=str)[:12000],
            })

    return {"content": "", "messages": convo, "error": "max tool rounds reached"}


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
