#!/usr/bin/env python3
"""CLI: risk checks and limits."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.risk import check_risk, limits, RiskState, STATE


def main():
    parser = argparse.ArgumentParser(description="Risk management")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Check if a trade passes risk")
    p_check.add_argument("symbol")
    p_check.add_argument("size_usd", type=float)
    p_check.add_argument("--leverage", type=float, default=1.0)

    p_limits = sub.add_parser("limits", help="Show current risk limits")
    p_state = sub.add_parser("state", help="Show current risk state")
    p_reset = sub.add_parser("reset", help="Reset risk state (dev only)")

    args = parser.parse_args()

    if args.cmd == "check":
        result = check_risk(args.symbol, args.size_usd, args.leverage)
        print(json.dumps(result, default=str))
    elif args.cmd == "limits":
        print(json.dumps(limits(), default=str))
    elif args.cmd == "state":
        print(json.dumps({
            "trades_today": STATE.trades_today,
            "realized_pnl_today": STATE.realized_pnl_today,
            "open_positions": STATE.open_positions,
        }, default=str))
    elif args.cmd == "reset":
        STATE.trades_today = 0
        STATE.realized_pnl_today = 0.0
        STATE.open_positions.clear()
        print(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()