"""Monitor conditions: turn the LLM's stated patience into machine-checkable state.

When the agent says WAIT with monitor_condition="pullback_3_percent", we register
a Watch. Every tick we re-fetch price and evaluate. On trigger the agent re-analyzes.
This is what makes "waiting" an observable behaviour instead of a sentence.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Watch:
    symbol: str
    condition: str
    reference_price: float
    created_at: float = field(default_factory=time.time)
    memory_id: int | None = None
    triggered: bool = False
    triggered_at: float | None = None
    trigger_detail: str | None = None
    checks: int = 0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "condition": self.condition,
            "reference_price": self.reference_price,
            "age_s": round(time.time() - self.created_at, 1),
            "checks": self.checks,
            "triggered": self.triggered,
            "trigger_detail": self.trigger_detail,
            "memory_id": self.memory_id,
        }


def parse_condition(condition: str) -> dict:
    """Translate the constrained condition vocabulary into an evaluable spec."""
    if not condition:
        return {"type": "none"}
    c = condition.strip().lower()

    m = re.fullmatch(r"pullback_(\d+(?:\.\d+)?)_percent", c)
    if m:
        return {"type": "pullback", "pct": float(m.group(1))}

    m = re.fullmatch(r"breakout_above_(\d+(?:\.\d+)?)", c)
    if m:
        return {"type": "breakout", "price": float(m.group(1))}

    m = re.fullmatch(r"rsi_below_(\d+(?:\.\d+)?)", c)
    if m:
        return {"type": "rsi_below", "level": float(m.group(1))}

    if c == "volume_normalizes":
        return {"type": "volume_normalizes"}

    return {"type": "unknown", "raw": condition}


def evaluate(watch: Watch, *, price: float, rsi: float | None,
             volume_ratio: float | None) -> dict:
    """Return {"triggered": bool, "detail": str} for the current market snapshot."""
    spec = parse_condition(watch.condition)
    kind = spec["type"]

    if kind == "pullback":
        target = watch.reference_price * (1 - spec["pct"] / 100)
        drop_pct = (watch.reference_price - price) / watch.reference_price * 100
        return {
            "triggered": price <= target,
            "detail": f"price {price:.4f} vs target {target:.4f} "
                      f"(-{drop_pct:.2f}% from {watch.reference_price:.4f}, "
                      f"need -{spec['pct']:.2f}%)",
        }

    if kind == "breakout":
        return {
            "triggered": price >= spec["price"],
            "detail": f"price {price:.4f} vs breakout {spec['price']:.4f}",
        }

    if kind == "rsi_below":
        if rsi is None:
            return {"triggered": False, "detail": "rsi unavailable"}
        return {
            "triggered": rsi <= spec["level"],
            "detail": f"rsi {rsi:.2f} vs level {spec['level']:.2f}",
        }

    if kind == "volume_normalizes":
        if volume_ratio is None:
            return {"triggered": False, "detail": "volume ratio unavailable"}
        return {
            "triggered": volume_ratio <= 1.3,
            "detail": f"volume ratio {volume_ratio:.2f} vs normal threshold 1.30",
        }

    return {"triggered": False, "detail": f"condition not machine-checkable: {kind}"}


class WatchList:
    def __init__(self) -> None:
        self._watches: list[Watch] = []

    def add(self, symbol: str, condition: str, reference_price: float,
            memory_id: int | None = None) -> Watch | None:
        spec = parse_condition(condition)
        if spec["type"] in ("none", "unknown"):
            return None
        w = Watch(symbol=symbol, condition=condition,
                  reference_price=reference_price, memory_id=memory_id)
        # Replace any existing watch for the same symbol.
        self._watches = [x for x in self._watches if x.symbol != symbol]
        self._watches.append(w)
        return w

    def active(self) -> list[Watch]:
        return [w for w in self._watches if not w.triggered]

    def all(self) -> list[Watch]:
        return list(self._watches)

    def drop(self, symbol: str) -> None:
        self._watches = [w for w in self._watches if w.symbol != symbol]

    def check_all(self, snapshot_fn: Any) -> list[dict]:
        """snapshot_fn(symbol) -> {price, rsi, volume_ratio}. Returns fired events."""
        fired = []
        for w in self.active():
            snap = snapshot_fn(w.symbol)
            w.checks += 1
            res = evaluate(w, price=snap["price"], rsi=snap.get("rsi"),
                           volume_ratio=snap.get("volume_ratio"))
            if res["triggered"]:
                w.triggered = True
                w.triggered_at = time.time()
                w.trigger_detail = res["detail"]
                fired.append({"symbol": w.symbol, "condition": w.condition,
                              "detail": res["detail"], "memory_id": w.memory_id,
                              "waited_s": round(w.triggered_at - w.created_at, 1)})
        return fired

    def to_dict(self) -> list[dict]:
        return [w.to_dict() for w in self._watches]
