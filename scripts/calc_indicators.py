#!/usr/bin/env python3
"""CLI: calculate technical indicators from candles JSON (stdin or --candles-file)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.indicators import calculate_indicators


def main():
    parser = argparse.ArgumentParser(description="Calculate indicators")
    parser.add_argument("--candles-file", help="Path to JSON file with candles list")
    parser.add_argument("--symbol", help="Symbol (for mock candles when no file)")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    candles = None
    if args.candles_file:
        with open(args.candles_file) as f:
            data = json.load(f)
            candles = data.get("candles", data) if isinstance(data, dict) else data
    elif args.symbol:
        from app.tools.binance_mcp import get_market_data
        data = get_market_data(args.symbol, args.interval, args.limit)
        candles = data.get("candles", [])
    else:
        # Read from stdin
        try:
            data = json.load(sys.stdin)
            candles = data.get("candles", data) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            print(json.dumps({"error": "no candles provided"}), file=sys.stderr)
            sys.exit(1)

    if not candles:
        print(json.dumps({"error": "empty candles"}), file=sys.stderr)
        sys.exit(1)

    ind = calculate_indicators(candles)
    print(json.dumps(ind, default=str))


if __name__ == "__main__":
    main()