"""CLI entry point for bStocks agent — callable from Claude Code custom agent.

Usage:
    python3 -m app.cli scan [--goal GOAL] [--top N]
    python3 -m app.cli cycle [--goal GOAL]
    python3 -m app.cli watch
    python3 -m app.cli risk
    python3 -m app.cli memory <symbol>
    python3 -m app.cli state
"""
from __future__ import annotations

import argparse
import json
import sys

from .agent.agent import Agent
from .tools import risk as risk_mod
from .tools import memory as mem
from .tools.binance_mcp import get_market_data
from .tools.indicators import calculate_indicators
from .tools.volume import volume_anomaly, momentum
from .tools.signals import score_candidate


def cmd_scan(args: argparse.Namespace) -> int:
    agent = Agent()
    top = agent.scan(agent._empty_trace(), top_n=args.top)
    print(json.dumps(top, indent=2, default=str))
    return 0


def cmd_cycle(args: argparse.Namespace) -> int:
    agent = Agent()
    out = agent.cycle(args.goal)
    decision = out.get("decision")
    risk = out.get("risk")
    trace_path = out.get("trace_path")
    print(json.dumps({
        "decision": decision,
        "risk": risk,
        "trace_path": trace_path,
    }, indent=2, default=str))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    agent = Agent()
    fired = agent.check_watches()
    print(json.dumps(fired, indent=2, default=str))
    return 0


def cmd_risk(args: argparse.Namespace) -> int:
    limits = risk_mod.limits()
    state = {
        "trades_today": risk_mod.STATE.trades_today,
        "realized_pnl_today": risk_mod.STATE.realized_pnl_today,
        "open_positions": risk_mod.STATE.open_positions,
    }
    print(json.dumps({"limits": limits, "state": state}, indent=2))
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    agent = Agent()
    c = agent._candles(args.symbol)
    ind = calculate_indicators(c)
    fp = mem.fingerprint(ind, volume_anomaly(c), momentum(c))
    similar = mem.search_memory(args.symbol, fp)
    stats = mem.outcome_stats(fp)
    print(json.dumps({
        "symbol": args.symbol,
        "fingerprint": fp,
        "similar_past_setups": similar,
        "historical_stats": stats,
    }, indent=2, default=str))
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    agent = Agent()
    watches = agent.watchlist.to_dict()
    print(json.dumps({
        "watches": watches,
        "last_decision": agent.last_decision,
        "pending_trade": agent.pending_trade,
    }, indent=2, default=str))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    agent = Agent()
    out = agent.confirm_trade()
    out.pop("trace", None)
    print(json.dumps(out, indent=2, default=str))
    return 0


class _EmptyTrace:
    def add(self, *a, **kw): pass
    def save(self): return ""

Agent._empty_trace = lambda self: _EmptyTrace()


def main() -> int:
    parser = argparse.ArgumentParser(prog="bstocks", description="bStocks AI Agent CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan universe for top candidates")
    p_scan.add_argument("--goal", default="Find the best bStocks opportunity with moderate risk. Do not trade unless the setup meets all risk criteria.")
    p_scan.add_argument("--top", type=int, default=4)
    p_scan.set_defaults(func=cmd_scan)

    p_cycle = sub.add_parser("cycle", help="Run one decision cycle (scan -> LLM -> risk gate)")
    p_cycle.add_argument("--goal", default="Find the best bStocks opportunity with moderate risk. Do not trade unless the setup meets all risk criteria.")
    p_cycle.set_defaults(func=cmd_cycle)

    p_watch = sub.add_parser("watch", help="Check active watch conditions")
    p_watch.set_defaults(func=cmd_watch)

    p_risk = sub.add_parser("risk", help="Show risk limits and current usage")
    p_risk.set_defaults(func=cmd_risk)

    p_mem = sub.add_parser("memory", help="Recall similar past setups for a symbol")
    p_mem.add_argument("symbol", help="Symbol like NVDAUSDT")
    p_mem.set_defaults(func=cmd_memory)

    p_state = sub.add_parser("state", help="Show agent internal state (watches, pending trade)")
    p_state.set_defaults(func=cmd_state)

    p_confirm = sub.add_parser("confirm", help="Execute pending trade after user confirmation")
    p_confirm.set_defaults(func=cmd_confirm)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())