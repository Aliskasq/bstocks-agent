"""Day-1 vertical slice check:
    python3 -m app.demo "Find the best moderate-risk bStock opportunity"
"""
import sys

from .agent.agent import Agent


def main() -> None:
    goal = sys.argv[1] if len(sys.argv) > 1 else (
        "Find the best bStocks opportunity with moderate risk. "
        "Do not trade unless the setup meets all risk criteria."
    )
    agent = Agent()
    out = agent.cycle(goal)
    print(out["trace"].pretty())
    print("\n--- FINAL ---")
    print("decision:", out.get("decision"))
    print("risk:", out.get("risk"))
    print("trace saved:", out.get("trace_path"))


if __name__ == "__main__":
    main()
