#!/usr/bin/env python3
"""CLI: Run a full bStocks agent decision cycle.

Usage:
  python -m scripts.run_agent "GOAL" [--model MODEL]

The agent will:
  1. Score universe (deterministic pre-filter)
  2. Investigate top candidates with tools
  3. Recall memory
  4. Reason → BUY/WAIT/AVOID
  5. Risk gate
  6. Save to memory
  7. Register monitor if WAIT
  8. Return decision JSON
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.agent import Agent
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL


def main():
    parser = argparse.ArgumentParser(description="Run bStocks agent cycle")
    parser.add_argument("goal", help="Trading goal (e.g. 'Find oversold quality bStocks for swing')")
    parser.add_argument("--model", default=OPENROUTER_MODEL, help="OpenRouter model ID")
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        print(json.dumps({"error": "OPENROUTER_API_KEY not set"}), file=sys.stderr)
        sys.exit(1)

    agent = Agent()
    result = agent.cycle(args.goal)

    decision = result.get("decision")
    trace = result.get("trace")
    trace_path = result.get("trace_path")

    output = {
        "goal": args.goal,
        "decision": decision,
        "trace_path": str(trace_path) if trace_path else None,
        "risk": result.get("risk"),
        "candidates": result.get("candidates"),
    }
    print(json.dumps(output, default=str))


if __name__ == "__main__":
    main()