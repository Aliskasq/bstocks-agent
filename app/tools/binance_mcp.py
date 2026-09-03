"""Binance Agent OS (MCP) client.

Speaks JSON-RPC 2.0 over the streamable-HTTP MCP endpoint:
    POST https://agent.binance.com/mcp/agentic

Flow: initialize -> tools/list -> tools/call.
Falls back to synthetic candles only when ALLOW_MOCK_MARKET=1 (dev), never in demo.
"""
from __future__ import annotations

import json
import math
import random
import time
from typing import Any

import httpx

from ..config import ALLOW_MOCK_MARKET, BINANCE_MCP_TOKEN, BINANCE_MCP_URL


class McpError(RuntimeError):
    pass


class BinanceMCP:
    def __init__(self, url: str = BINANCE_MCP_URL, token: str = BINANCE_MCP_TOKEN):
        self.url = url
        # Prefer an OAuth token obtained via the PKCE flow; fall back to a
        # static env token only if one was explicitly provided.
        if not token:
            try:
                from ..services.binance_oauth import get_access_token
                token = get_access_token() or ""
            except Exception:
                token = ""
        self.token = token
        self._id = 0
        self._session_id: str | None = None
        self._initialized = False
        self._tools: list[dict] | None = None

    # ---- plumbing -------------------------------------------------
    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
        ctype = resp.headers.get("content-type", "")
        text = resp.text
        if "text/event-stream" in ctype:
            for line in text.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if "result" in obj or "error" in obj:
                            return obj
            raise McpError(f"no JSON-RPC payload in SSE: {text[:300]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(f"bad JSON from MCP: {text[:300]}") from exc

    def _rpc(self, method: str, params: dict | None = None, *, notify: bool = False) -> Any:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            body["id"] = self._next_id()
        with httpx.Client(timeout=30) as client:
            resp = client.post(self.url, json=body, headers=self._headers())
            sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            if sid:
                self._session_id = sid
            if notify:
                return None
            if resp.status_code >= 400:
                raise McpError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            obj = self._parse(resp)
        if "error" in obj:
            raise McpError(json.dumps(obj["error"])[:400])
        return obj.get("result")

    def initialize(self) -> dict:
        if self._initialized:
            return {"already": True}
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bstocks-ai-agent", "version": "0.1.0"},
            },
        )
        self._rpc("notifications/initialized", {}, notify=True)
        self._initialized = True
        return result or {}

    def list_tools(self) -> list[dict]:
        if self._tools is not None:
            return self._tools
        self.initialize()
        result = self._rpc("tools/list", {}) or {}
        self._tools = result.get("tools", [])
        return self._tools

    def call(self, name: str, arguments: dict) -> Any:
        self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments}) or {}
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    txt = item.get("text", "")
                    try:
                        return json.loads(txt)
                    except json.JSONDecodeError:
                        return txt
        return result

    # ---- discovery helper ----------------------------------------
    def find_tool(self, *keywords: str) -> str | None:
        """Pick the first MCP tool whose name contains all keywords."""
        for tool in self.list_tools():
            name = tool.get("name", "").lower()
            if all(k.lower() in name for k in keywords):
                return tool["name"]
        return None


# ---- market data facade -------------------------------------------

# Dev-only clock: advancing this makes mock series evolve so monitor
# conditions (pullbacks, breakouts) can actually fire during a demo run.
_MOCK_TICK = 0


def advance_mock_clock(steps: int = 1) -> int:
    global _MOCK_TICK
    _MOCK_TICK += steps
    return _MOCK_TICK


def mock_clock() -> int:
    return _MOCK_TICK


def _mock_candles(symbol: str, n: int = 120) -> list[dict]:
    """Deterministic-ish synthetic series for offline development."""
    rnd = random.Random(hash(symbol) & 0xFFFF)
    price = 100 + (hash(symbol) % 120)
    out = []
    # Generate extra bars so the mock clock can slide a window forward.
    total = n + _MOCK_TICK
    for i in range(total):
        drift = math.sin(i / 14) * 0.6 + rnd.uniform(-0.7, 0.8)
        price = max(1.0, price * (1 + drift / 100))
        high = price * (1 + abs(rnd.uniform(0, 0.006)))
        low = price * (1 - abs(rnd.uniform(0, 0.006)))
        vol = rnd.uniform(8e5, 1.6e6) * (3.2 if i == n - 1 else 1.0)
        out.append({
            "open": round(price * (1 - rnd.uniform(0, 0.003)), 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(price, 4),
            "volume": round(vol, 2),
            "ts": int(time.time()) - (total - i) * 3600,
        })
    # Slide the window: later ticks reveal later bars (price can pull back).
    return out[_MOCK_TICK:_MOCK_TICK + n]


def _normalize_candles(raw: Any) -> list[dict]:
    """Accept a few plausible MCP kline shapes and normalize."""
    rows = raw
    if isinstance(raw, dict):
        for key in ("klines", "candles", "data", "result", "list"):
            if isinstance(raw.get(key), list):
                rows = raw[key]
                break
    if not isinstance(rows, list):
        raise McpError(f"unrecognized candle payload: {str(raw)[:200]}")
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append({
                "open": float(r.get("open", r.get("o", 0))),
                "high": float(r.get("high", r.get("h", 0))),
                "low": float(r.get("low", r.get("l", 0))),
                "close": float(r.get("close", r.get("c", 0))),
                "volume": float(r.get("volume", r.get("v", 0))),
                "ts": r.get("openTime", r.get("t", r.get("ts"))),
            })
        elif isinstance(r, (list, tuple)) and len(r) >= 6:
            out.append({
                "ts": r[0], "open": float(r[1]), "high": float(r[2]),
                "low": float(r[3]), "close": float(r[4]), "volume": float(r[5]),
            })
    if not out:
        raise McpError("no candles parsed")
    return out


def get_market_data(symbol: str, interval: str = "1h", limit: int = 120,
                    mcp: BinanceMCP | None = None) -> dict:
    """Return normalized candles for a bStock symbol.

    Tries the live MCP endpoint first; only uses mock data if explicitly allowed.
    """
    client = mcp or BinanceMCP()
    source = "binance_mcp"
    try:
        tool = (client.find_tool("kline") or client.find_tool("candle")
                or client.find_tool("ohlc") or client.find_tool("market", "data"))
        if not tool:
            raise McpError(
                "no kline-like tool exposed; available: "
                + ", ".join(t.get("name", "?") for t in client.list_tools())[:300]
            )
        raw = client.call(tool, {"symbol": symbol, "interval": interval, "limit": limit})
        candles = _normalize_candles(raw)
    except Exception as exc:  # noqa: BLE001
        if not ALLOW_MOCK_MARKET:
            raise
        candles = _mock_candles(symbol, limit)
        source = f"mock (mcp unavailable: {type(exc).__name__}: {str(exc)[:120]})"
    return {
        "symbol": symbol,
        "interval": interval,
        "source": source,
        "candles": candles,
        "last_price": candles[-1]["close"],
    }
