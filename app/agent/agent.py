"""The agent: scanner + tool registry + decision cycle."""
from __future__ import annotations

import json
from typing import Callable

from ..services.openrouter import ToolRegistry, chat_with_tools, extract_json
from ..tools import memory as mem
from ..tools import risk as risk_mod
from ..tools.binance_mcp import BinanceMCP, get_market_data
from ..tools.indicators import calculate_indicators
from ..tools.signals import score_candidate
from ..tools.volume import momentum, volatility, volume_anomaly
from ..trace import Trace
from .monitor import WatchList
from .prompts import DECISION_USER_TEMPLATE, REANALYSIS_USER_TEMPLATE, SYSTEM

# bStocks universe for the MVP demo. Kept small on purpose.
UNIVERSE = ["NVDAUSDT", "TSLAUSDT", "AAPLUSDT", "AMZNUSDT", "MSFTUSDT", "METAUSDT"]


class Agent:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.mcp = BinanceMCP()
        self.on_event = on_event
        self._candle_cache: dict[str, list[dict]] = {}
        self.watchlist = WatchList()
        self.last_decision: dict | None = None
        self.pending_trade: dict | None = None

    # ---- data access -------------------------------------------------
    def _candles(self, symbol: str, interval: str = "1h", limit: int = 120) -> list[dict]:
        key = f"{symbol}:{interval}"
        if key not in self._candle_cache:
            data = get_market_data(symbol, interval, limit, mcp=self.mcp)
            self._candle_cache[key] = data["candles"]
            self._last_source = data["source"]
        return self._candle_cache[key]

    def invalidate(self) -> None:
        self._candle_cache.clear()

    def snapshot(self, symbol: str) -> dict:
        """Cheap current-state read used by the monitor (no LLM involved)."""
        c = self._candles(symbol)
        ind = calculate_indicators(c)
        return {
            "symbol": symbol,
            "price": ind["price"],
            "rsi": ind["rsi"],
            "volume_ratio": volume_anomaly(c).get("ratio"),
        }

    # ---- scanner -----------------------------------------------------
    def scan(self, trace: Trace, top_n: int = 4) -> list[dict]:
        """Deterministic prefilter: score the whole universe in Python, keep the best."""
        trace.add("scan_start", universe=UNIVERSE)
        scored = []
        for sym in UNIVERSE:
            try:
                scored.append(score_candidate(sym, self._candles(sym)))
            except Exception as exc:  # noqa: BLE001
                trace.add("scan_error", symbol=sym, error=str(exc)[:200])
        scored.sort(key=lambda s: s["signal_score"], reverse=True)
        top = scored[:top_n]
        trace.add("scan_result", ranked=[
            {"symbol": s["symbol"], "score": s["signal_score"], "label": s["label"]}
            for s in scored
        ])
        return top

    # ---- tools exposed to the LLM ------------------------------------
    def build_registry(self, trace: Trace) -> ToolRegistry:
        reg = ToolRegistry()

        def t_market(symbol: str, interval: str = "1h"):
            c = self._candles(symbol, interval)
            return {"symbol": symbol, "interval": interval, "last_price": c[-1]["close"],
                    "candles_available": len(c),
                    "recent_closes": [x["close"] for x in c[-12:]]}

        def t_indicators(symbol: str):
            return calculate_indicators(self._candles(symbol))

        def t_flow(symbol: str):
            c = self._candles(symbol)
            return {"volume_anomaly": volume_anomaly(c), "volatility": volatility(c),
                    "momentum": momentum(c)}

        def t_score(symbol: str):
            s = score_candidate(symbol, self._candles(symbol))
            return {k: s[k] for k in ("symbol", "signal_score", "label", "components",
                                      "range_position_pct")}

        def t_get_memory(symbol: str):
            c = self._candles(symbol)
            ind = calculate_indicators(c)
            fp = mem.fingerprint(ind, volume_anomaly(c), momentum(c))
            return {"fingerprint": fp,
                    "similar_past_setups": mem.search_memory(symbol, fp),
                    "historical_stats": mem.outcome_stats(fp)}

        def t_limits():
            return risk_mod.limits() | {
                "trades_used_today": risk_mod.STATE.trades_today,
                "realized_pnl_today": risk_mod.STATE.realized_pnl_today,
            }

        reg.register("get_market_data",
                     "Live bStocks price data via Binance Agent OS (MCP).",
                     {"type": "object", "properties": {
                         "symbol": {"type": "string"},
                         "interval": {"type": "string", "enum": ["15m", "1h", "4h", "1d"]}},
                      "required": ["symbol"]}, t_market)

        reg.register("calculate_indicators",
                     "RSI, EMA20/50, MACD, ATR computed in Python from live candles.",
                     {"type": "object", "properties": {"symbol": {"type": "string"}},
                      "required": ["symbol"]}, t_indicators)

        reg.register("analyze_flow",
                     "Volume anomaly ratio, volatility regime and momentum.",
                     {"type": "object", "properties": {"symbol": {"type": "string"}},
                      "required": ["symbol"]}, t_flow)

        reg.register("get_signal_score",
                     "Deterministic 0-100 signal score with component breakdown.",
                     {"type": "object", "properties": {"symbol": {"type": "string"}},
                      "required": ["symbol"]}, t_score)

        reg.register("get_memory",
                     "Recall past similar setups for this symbol and their outcomes.",
                     {"type": "object", "properties": {"symbol": {"type": "string"}},
                      "required": ["symbol"]}, t_get_memory)

        reg.register("get_risk_limits",
                     "Current hard risk limits and today's usage.",
                     {"type": "object", "properties": {}}, t_limits)

        return reg

    # ---- one decision cycle -----------------------------------------
    def cycle(self, goal: str) -> dict:
        trace = Trace(goal, on_event=self.on_event)
        self.invalidate()

        top = self.scan(trace)
        if not top:
            trace.add("abort", reason="no candidates")
            trace.save()
            return {"trace": trace, "decision": None}

        candidates_txt = json.dumps([
            {"symbol": s["symbol"], "signal_score": s["signal_score"],
             "label": s["label"], "components": s["components"],
             "price": s["indicators"]["price"], "rsi": s["indicators"]["rsi"],
             "trend": s["indicators"]["ema_cross"],
             "volume_ratio": s["volume_anomaly"]["ratio"],
             "volatility": s["volatility"]["verdict"]}
            for s in top
        ], indent=2)

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": DECISION_USER_TEMPLATE.format(
                goal=goal,
                limits=json.dumps(risk_mod.limits(), indent=2),
                candidates=candidates_txt,
            )},
        ]

        return self._run_decision(messages, trace, scores=top)

    # ---- shared decision runner --------------------------------------
    def _run_decision(self, messages: list[dict], trace: Trace,
                      scores: list[dict] | None = None) -> dict:
        registry = self.build_registry(trace)
        result = chat_with_tools(messages, registry, trace, response_json=True)
        decision = extract_json(result.get("content", "")) or {}

        if not decision:
            trace.add("decision_parse_failed", raw=result.get("content", "")[:500])
            trace.save()
            return {"trace": trace, "decision": None}

        trace.decision(decision)

        # Risk gate — the LLM's proposal is only a request.
        risk_verdict = None
        if decision.get("decision") == "BUY":
            size = float(decision.get("proposed_size_usd") or 0)
            risk_verdict = risk_mod.check_risk(decision.get("symbol", "?"), size)
            trace.risk(risk_verdict)
            decision["final_action"] = (
                "AWAITING_USER_CONFIRMATION" if risk_verdict["approved"]
                else "REJECTED_BY_RISK"
            )
        else:
            decision["final_action"] = decision.get("decision")

        # Remember this setup.
        sym = decision.get("symbol")
        mem_id = None
        if sym:
            try:
                c = self._candles(sym)
                ind = calculate_indicators(c)
                fp = mem.fingerprint(ind, volume_anomaly(c), momentum(c))
                score = None
                if scores:
                    score = next((s["signal_score"] for s in scores
                                  if s["symbol"] == sym), None)
                if score is None:
                    score = score_candidate(sym, c)["signal_score"]
                mem_id = mem.save_memory(sym, fp, score, ind, decision)
                trace.add("memory_saved", memory_id=mem_id, fingerprint=fp)
            except Exception as exc:  # noqa: BLE001
                trace.add("memory_error", error=str(exc)[:200])

        # Register the monitor condition so WAIT becomes observable state.
        if decision.get("decision") == "WAIT" and decision.get("monitor_condition"):
            ref = self.snapshot(sym)["price"] if sym else None
            if ref:
                w = self.watchlist.add(sym, decision["monitor_condition"], ref, mem_id)
                if w:
                    trace.add("watch_registered", **w.to_dict())
                else:
                    trace.add("watch_rejected",
                              condition=decision["monitor_condition"],
                              reason="condition not machine-checkable")

        if decision.get("final_action") == "AWAITING_USER_CONFIRMATION":
            self.pending_trade = {
                "symbol": sym,
                "size_usd": risk_verdict["approved_size_usd"],
                "entry_price": self.snapshot(sym)["price"],
                "memory_id": mem_id,
                "decision": decision,
            }

        self.last_decision = decision
        path = trace.save()
        return {"trace": trace, "decision": decision, "risk": risk_verdict,
                "memory_id": mem_id, "trace_path": path, "candidates": scores}

    # ---- monitoring --------------------------------------------------
    def check_watches(self) -> list[dict]:
        """Evaluate all active watches against fresh data. No LLM cost."""
        self.invalidate()
        return self.watchlist.check_all(self.snapshot)

    def reanalyze(self, goal: str, fired: dict) -> dict:
        """A monitor condition triggered — re-verify from scratch."""
        trace = Trace(f"[re-analysis] {goal}", on_event=self.on_event)
        self.invalidate()
        symbol = fired["symbol"]
        watch = next((w for w in self.watchlist.all() if w.symbol == symbol), None)
        prev_reason = (self.last_decision or {}).get("reason", "(not recorded)")

        trace.add("trigger", symbol=symbol, condition=fired["condition"],
                  detail=fired["detail"], waited_s=fired.get("waited_s"))

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": REANALYSIS_USER_TEMPLATE.format(
                goal=goal, symbol=symbol, condition=fired["condition"],
                detail=fired["detail"], waited_s=fired.get("waited_s", "?"),
                checks=watch.checks if watch else "?",
                previous_reason=prev_reason,
                limits=json.dumps(risk_mod.limits(), indent=2),
            )},
        ]
        out = self._run_decision(messages, trace)
        self.watchlist.drop(symbol)
        return out

    # ---- trade execution (gated) -------------------------------------
    def confirm_trade(self) -> dict:
        """User-confirmed execution path: risk re-check -> MCP order -> verify."""
        if not self.pending_trade:
            return {"error": "no pending trade"}

        pt = self.pending_trade
        trace = Trace(f"[execute] {pt['symbol']}", on_event=self.on_event)

        # Re-check risk at execution time, not just at decision time.
        verdict = risk_mod.check_risk(pt["symbol"], pt["size_usd"])
        trace.risk(verdict)
        if not verdict["approved"]:
            self.pending_trade = None
            trace.add("execution_aborted", reason=verdict["reason"])
            trace.save()
            return {"executed": False, "reason": verdict["reason"], "trace": trace}

        order = {"symbol": pt["symbol"], "side": "BUY", "type": "MARKET",
                 "quoteOrderQty": pt["size_usd"]}
        trace.tool_call("binance_place_order", order)
        try:
            tool = (self.mcp.find_tool("order", "place") or self.mcp.find_tool("order")
                    or self.mcp.find_tool("trade"))
            if not tool:
                raise RuntimeError("no order tool exposed by Agent OS")
            result = self.mcp.call(tool, order)
            executed = True
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            executed = False
        trace.tool_result("binance_place_order", result)

        if executed:
            risk_mod.STATE.record_trade(pt["symbol"], pt["size_usd"])
            trace.add("position_opened", symbol=pt["symbol"],
                      size_usd=pt["size_usd"], entry=pt["entry_price"])

        self.pending_trade = None
        trace.save()
        return {"executed": executed, "order": order, "result": result,
                "trace": trace, "risk": verdict}

    def close_position(self, symbol: str, exit_price: float,
                       memory_id: int | None = None) -> dict:
        """Close the loop: record the outcome so memory becomes useful."""
        entry = risk_mod.STATE.open_positions.get(symbol)
        out: dict = {"symbol": symbol}
        if memory_id:
            out |= mem.record_outcome(memory_id, entry or exit_price, exit_price)
            risk_mod.STATE.record_pnl(
                (out.get("pnl_pct") or 0) / 100 * (entry or 0))
        risk_mod.STATE.open_positions.pop(symbol, None)
        return out
