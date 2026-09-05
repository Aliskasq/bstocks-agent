#!/usr/bin/env python3
"""CLI: memory operations — save, search, stats, record_outcome."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.memory import (
    fingerprint, save_memory, search_memory, outcome_stats, record_outcome
)
from app.tools.indicators import calculate_indicators
from app.tools.volume import volume_anomaly, momentum
from app.tools.binance_mcp import get_market_data


def main():
    parser = argparse.ArgumentParser(description="Memory operations")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fp = sub.add_parser("fingerprint", help="Compute fingerprint for symbol")
    p_fp.add_argument("symbol")
    p_fp.add_argument("--interval", default="1h")
    p_fp.add_argument("--limit", type=int, default=120)

    p_save = sub.add_parser("save", help="Save a decision to memory")
    p_save.add_argument("symbol")
    p_save.add_argument("decision_json", help="Decision JSON string or @file")
    p_save.add_argument("--signal-score", type=float)
    p_save.add_argument("--interval", default="1h")
    p_save.add_argument("--limit", type=int, default=120)

    p_search = sub.add_parser("search", help="Search similar past setups")
    p_search.add_argument("--symbol")
    p_search.add_argument("--fingerprint")
    p_search.add_argument("--limit", type=int, default=5)

    p_stats = sub.add_parser("stats", help="Outcome stats for a fingerprint")
    p_stats.add_argument("fingerprint")

    p_outcome = sub.add_parser("outcome", help="Record trade outcome")
    p_outcome.add_argument("memory_id", type=int)
    p_outcome.add_argument("entry", type=float)
    p_outcome.add_argument("exit", type=float)

    args = parser.parse_args()

    if args.cmd == "fingerprint":
        data = get_market_data(args.symbol, args.interval, args.limit)
        candles = data.get("candles", [])
        ind = calculate_indicators(candles)
        vol = volume_anomaly(candles)
        mom = momentum(candles)
        fp = fingerprint(ind, vol, mom)
        print(json.dumps({"symbol": args.symbol, "fingerprint": fp, "indicators": ind}))

    elif args.cmd == "save":
        decision = json.loads(args.decision_json) if not args.decision_json.startswith("@") \
            else json.load(open(args.decision_json[1:]))
        data = get_market_data(args.symbol, args.interval, args.limit)
        candles = data.get("candles", [])
        ind = calculate_indicators(candles)
        vol = volume_anomaly(candles)
        mom = momentum(candles)
        fp = fingerprint(ind, vol, mom)
        score = args.signal_score
        if score is None:
            from app.tools.signals import score_candidate
            score = score_candidate(args.symbol, candles)["signal_score"]
        mem_id = save_memory(args.symbol, fp, score, ind, decision)
        print(json.dumps({"memory_id": mem_id, "fingerprint": fp}))

    elif args.cmd == "search":
        results = search_memory(args.symbol, args.fingerprint, args.limit)
        print(json.dumps(results, default=str))

    elif args.cmd == "stats":
        stats = outcome_stats(args.fingerprint)
        print(json.dumps(stats, default=str))

    elif args.cmd == "outcome":
        result = record_outcome(args.memory_id, args.entry, args.exit)
        print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()