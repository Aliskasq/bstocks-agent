#!/usr/bin/env python3
"""CLI: score all universe candidates or a specific symbol."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.signals import score_candidate
from app.tools.binance_mcp import get_market_data
from app.agent.agent import UNIVERSE


def main():
    parser = argparse.ArgumentParser(description="Score candidates")
    parser.add_argument("--symbol", help="Single symbol to score")
    parser.add_argument("--top-n", type=int, default=4, help="Top N from universe")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    if args.symbol:
        data = get_market_data(args.symbol, args.interval, args.limit)
        candles = data.get("candles", [])
        result = score_candidate(args.symbol, candles)
        print(json.dumps(result, default=str))
        return

    # Score full universe
    scored = []
    for sym in UNIVERSE:
        try:
            data = get_market_data(sym, args.interval, args.limit)
            candles = data.get("candles", [])
            scored.append(score_candidate(sym, candles))
        except Exception as e:
            print(json.dumps({"symbol": sym, "error": str(e)}), file=sys.stderr)

    scored.sort(key=lambda s: s["signal_score"], reverse=True)
    top = scored[:args.top_n]
    print(json.dumps({
        "ranked": [
            {"symbol": s["symbol"], "score": s["signal_score"], "label": s["label"]}
            for s in scored
        ],
        "top": top
    }, default=str))


if __name__ == "__main__":
    main()