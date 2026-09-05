#!/usr/bin/env python3
"""CLI: Binance Agent OS MCP operations — list tools, call tool, place order."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools.binance_mcp import BinanceMCP


def main():
    parser = argparse.ArgumentParser(description="Binance Agent OS MCP client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tools = sub.add_parser("tools", help="List available MCP tools")
    p_call = sub.add_parser("call", help="Call an MCP tool")
    p_call.add_argument("name", help="Tool name")
    p_call.add_argument("args_json", nargs="?", default="{}", help="Arguments JSON")
    p_order = sub.add_parser("order", help="Place order via MCP")
    p_order.add_argument("symbol")
    p_order.add_argument("side", choices=["BUY", "SELL"])
    p_order.add_argument("type", choices=["MARKET", "LIMIT"])
    p_order.add_argument("--quoteOrderQty", type=float, help="Quote quantity for MARKET BUY")
    p_order.add_argument("--quantity", type=float, help="Base quantity")
    p_order.add_argument("--price", type=float, help="Limit price")

    args = parser.parse_args()

    client = BinanceMCP()

    if args.cmd == "tools":
        tools = client.list_tools()
        print(json.dumps(tools, default=str))
    elif args.cmd == "call":
        arguments = json.loads(args.args_json)
        result = client.call(args.name, arguments)
        print(json.dumps(result, default=str))
    elif args.cmd == "order":
        order = {
            "symbol": args.symbol,
            "side": args.side,
            "type": args.type,
        }
        if args.quoteOrderQty is not None:
            order["quoteOrderQty"] = args.quoteOrderQty
        if args.quantity is not None:
            order["quantity"] = args.quantity
        if args.price is not None:
            order["price"] = args.price
        # Find order tool
        tool = (client.find_tool("order", "place") or client.find_tool("order")
                or client.find_tool("trade"))
        if not tool:
            print(json.dumps({"error": "no order tool found"}), file=sys.stderr)
            sys.exit(1)
        result = client.call(tool, order)
        print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()