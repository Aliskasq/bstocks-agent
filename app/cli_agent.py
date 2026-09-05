#!/usr/bin/env python3
"""CLI entrypoint for bStocks agent — invoke from Claude Code or terminal.

Usage:
    python -m app.cli_agent "Find the best bStocks opportunity with moderate risk"
    python -m app.cli_agent --goal "Your goal" --once  # single cycle, no loop
    python -m app.cli_agent --loop --interval 20      # autonomous loop
"""
from __future__ import annotations

import argparse
import json
import sys
import os

# Ensure we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.agent import Agent
from app.config import ALLOW_MOCK_MARKET
from app.tools import binance_mcp


def main() -> int:
    parser = argparse.ArgumentParser(description="bStocks AI Agent CLI")
    parser.add_argument("goal", nargs="?", help="Trading goal (e.g., 'Find moderate risk opportunity')")
    parser.add_argument("--model", help="OpenRouter model ID (overrides .env)")
    parser.add_argument("--once", action="store_true", help="Run single decision cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run autonomous loop (default if --once not set)")
    parser.add_argument("--interval", type=float, default=20.0, help="Monitor interval in seconds (loop mode)")
    parser.add_argument("--rescan", type=float, default=600.0, help="Rescan interval in seconds (loop mode)")
    parser.add_argument("--mock-speed", type=int, default=0, help="Advance mock clock per tick (dev)")
    parser.add_argument("--json", action="store_true", help="Output decision as JSON to stdout")
    parser.add_argument("--trace-dir", default="traces", help="Trace output directory")
    args = parser.parse_args()

    # Apply model override early so Agent picks it up
    if args.model:
        os.environ["OPENROUTER_MODEL"] = args.model
        from app.services import openrouter as llm
        llm.set_active_model(args.model)

    goal = args.goal or (
        "Find the best bStocks opportunity with moderate risk. "
        "Do not trade unless the setup meets all risk criteria."
    )

    print(f"🎯 Goal: {goal}", file=sys.stderr)
    print(f"📊 Mock market: {'ON' if ALLOW_MOCK_MARKET else 'OFF (real Binance MCP)'}", file=sys.stderr)

    # Instantiate agent
    agent = Agent()

    if args.once or not args.loop:
        # Single cycle
        print("🔄 Running single decision cycle...", file=sys.stderr)
        out = agent.cycle(goal)

        decision = out.get("decision")
        trace = out.get("trace")
        risk = out.get("risk")

        if args.json:
            result = {
                "decision": decision,
                "risk": risk,
                "trace_id": trace.id if trace else None,
                "trace_path": out.get("trace_path"),
                "memory_id": out.get("memory_id"),
                "candidates": [
                    {"symbol": c["symbol"], "score": c["signal_score"], "label": c["label"]}
                    for c in (out.get("candidates") or [])
                ],
            }
            print(json.dumps(result, indent=2, default=str))
        else:
            if decision:
                print(f"\n✅ Decision: {decision.get('decision')}")
                print(f"   Symbol: {decision.get('symbol')}")
                print(f"   Confidence: {decision.get('confidence')}")
                print(f"   Reason: {decision.get('reason')}")
                if decision.get("proposed_size_usd"):
                    print(f"   Size: ${decision['proposed_size_usd']}")
                if decision.get("monitor_condition"):
                    print(f"   Monitor: {decision['monitor_condition']}")
                print(f"   Final Action: {decision.get('final_action')}")
            else:
                print("\n❌ No decision (parse failed or no candidates)")

            if risk:
                print(f"\n🛡️  Risk: {'APPROVED' if risk['approved'] else 'REJECTED'} — {risk['reason']}")
            if trace:
                print(f"\n📝 Trace saved: {out.get('trace_path')}")

        return 0 if decision else 1

    # Autonomous loop
    print(f"🔁 Starting autonomous loop (monitor={args.interval}s, rescan={args.rescan}s)...", file=sys.stderr)
    print("   Press Ctrl+C to stop", file=sys.stderr)

    from app.agent.loop import AgentLoop

    def on_event(event: dict) -> None:
        kind = event.get("kind", "event")
        if kind == "decision":
            d = event.get("decision") or {}
            action = d.get("final_action") or d.get("decision")
            sym = d.get("symbol", "?")
            print(f"\n[{event['ts']:.0f}] 🤖 Cycle {event.get('cycle')} | {action} | {sym}", file=sys.stderr)
            if d.get("reason"):
                print(f"   Reason: {d['reason']}", file=sys.stderr)
        elif kind == "condition_triggered":
            print(f"\n[{event['ts']:.0f}] 🔔 Trigger: {event['symbol']} — {event['condition']}", file=sys.stderr)
        elif kind == "status":
            print(f"\n[{event['ts']:.0f}] 📍 Status: {event['status']}", file=sys.stderr)
        elif kind == "error":
            print(f"\n[{event['ts']:.0f}] ❌ Error: {event['error']}", file=sys.stderr)

    loop = AgentLoop(
        goal,
        on_event=on_event,
        monitor_interval_s=args.interval,
        rescan_interval_s=args.rescan,
        mock_speed=args.mock_speed,
    )

    try:
        loop.start()
        # Keep main thread alive
        import time
        while loop.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping...", file=sys.stderr)
        loop.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())