"""Risk Manager — deterministic Python, deliberately OUTSIDE the LLM's control.

The LLM may request a trade. This module decides whether it is allowed.
Every rejection carries a human-readable reason for the dashboard + trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import (
    MAX_DAILY_LOSS_USD,
    MAX_LEVERAGE,
    MAX_POSITION_USD,
    MAX_TRADES_PER_DAY,
)


@dataclass
class RiskState:
    trades_today: int = 0
    realized_pnl_today: float = 0.0
    open_positions: dict[str, float] = field(default_factory=dict)

    def record_trade(self, symbol: str, size_usd: float) -> None:
        self.trades_today += 1
        self.open_positions[symbol] = self.open_positions.get(symbol, 0.0) + size_usd

    def record_pnl(self, pnl: float) -> None:
        self.realized_pnl_today += pnl


STATE = RiskState()


def check_risk(symbol: str, size_usd: float, leverage: float = 1.0,
               state: RiskState | None = None) -> dict:
    st = state or STATE
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    add("max_position",
        size_usd <= MAX_POSITION_USD,
        f"requested ${size_usd:.2f} vs limit ${MAX_POSITION_USD:.2f}")

    add("max_leverage",
        leverage <= MAX_LEVERAGE,
        f"requested {leverage}x vs limit {MAX_LEVERAGE}x")

    add("max_trades_per_day",
        st.trades_today < MAX_TRADES_PER_DAY,
        f"{st.trades_today} trades used of {MAX_TRADES_PER_DAY}")

    add("daily_loss_limit",
        st.realized_pnl_today > -MAX_DAILY_LOSS_USD,
        f"realized P&L today ${st.realized_pnl_today:.2f}, floor -${MAX_DAILY_LOSS_USD:.2f}")

    already = st.open_positions.get(symbol, 0.0)
    add("no_pyramiding",
        already + size_usd <= MAX_POSITION_USD,
        f"existing exposure ${already:.2f} + new ${size_usd:.2f} vs ${MAX_POSITION_USD:.2f}")

    add("positive_size", size_usd > 0, f"size ${size_usd:.2f}")

    failed = [c for c in checks if not c["ok"]]
    approved = not failed
    return {
        "approved": approved,
        "symbol": symbol,
        "requested_size_usd": size_usd,
        "approved_size_usd": size_usd if approved else 0.0,
        "checks": checks,
        "reason": "all risk checks passed" if approved
                  else "; ".join(c["detail"] for c in failed),
        "failed_checks": [c["check"] for c in failed],
    }


def limits() -> dict:
    return {
        "max_position_usd": MAX_POSITION_USD,
        "max_daily_loss_usd": MAX_DAILY_LOSS_USD,
        "max_trades_per_day": MAX_TRADES_PER_DAY,
        "max_leverage": MAX_LEVERAGE,
    }
