#!/usr/bin/env python3
"""CLI: get market candles for a symbol via Binance MCP (or mock)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Ensure app is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.binance_mcp import get_market_data


def main():
    parser = argparse.ArgumentParser(description="Get market candles")
    parser.add_argument("symbol", help="Symbol e.g. NVDAUSDT")
    parser.add_argument("--interval", default="1h", choices=["15m", "1h", "4h", "1d"])
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    try:
        data = get_market_data(args.symbol, args.interval, args.limit)
        print(json.dumps(data, default=str))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()