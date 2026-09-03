"""Day-2 exit criterion check: WAIT -> monitor -> trigger -> re-analysis.

Runs offline-fast: monitor every 1s, synthetic clock advanced so a pullback
actually materializes instead of waiting real hours.

    python3 -m app.demo_day2
"""
from __future__ import annotations

import json
import time

from .agent.loop import AgentLoop


def main() -> None:
    goal = ("Find the best bStocks opportunity with moderate risk. "
            "Do not trade unless the setup meets all risk criteria.")

    def on_event(ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "status":
            print(f"[status] {ev['status']}")
        elif kind == "watch_check":
            print(f"[watch]  {ev['symbol']} price={ev['price']} "
                  f"ref={ev['reference_price']} rsi={ev['rsi']} #{ev['checks']}")
        elif kind == "condition_triggered":
            print(f"\n*** TRIGGERED: {ev['symbol']} {ev['condition']}")
            print(f"    {ev['detail']}  (waited {ev['waited_s']}s)\n")
        elif kind == "decision":
            d = ev.get("decision") or {}
            tag = "RE-ANALYSIS" if ev.get("reanalysis") else "SCAN"
            print(f"\n=== {tag} decision #{ev['cycle']}: "
                  f"{d.get('symbol')} -> {d.get('decision')} "
                  f"(conf {d.get('confidence')})")
            print(f"    reason: {str(d.get('reason'))[:300]}")
            print(f"    monitor: {d.get('monitor_condition')}")
            print(f"    final_action: {d.get('final_action')}")
            if ev.get("risk"):
                r = ev["risk"]
                print(f"    RISK: approved={r['approved']} {r['reason']}")
            print()
        elif kind == "error":
            print(f"[error] {ev['error']}")

    loop = AgentLoop(goal, on_event=on_event, monitor_interval_s=1.0,
                     rescan_interval_s=5.0, mock_speed=3)

    print("Starting agent loop (fast mock clock)...\n")
    loop.start()

    deadline = time.time() + 240
    triggered = False
    while time.time() < deadline:
        time.sleep(2)
        evs = [e for e in loop.history if e["kind"] == "condition_triggered"]
        if evs and loop.cycles >= 2:
            triggered = True
            break
    loop.stop()
    time.sleep(1.5)

    print("\n" + "=" * 60)
    print("FINAL STATE")
    print(json.dumps(loop.state(), indent=2, default=str)[:2500])
    print("=" * 60)
    print("EXIT CRITERION (WAIT -> trigger -> re-analysis):",
          "PASS" if triggered else "NOT REACHED")


if __name__ == "__main__":
    main()
